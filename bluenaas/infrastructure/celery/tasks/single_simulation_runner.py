"""
This task is responsible for running a single instance of a neuron simulation based on the type of variation.

Overview:
---------
- Executes a single simulation instance, varying either the current or the frequency, depending on the configuration.
- The recording location is also used to distinguish between different simulation instances.

"""

import json

from loguru import logger
import numpy as np
import billiard  # type: ignore
from billiard.queues import Empty as QueueEmptyException  # type: ignore

from bluenaas.core.stimulation.common import setup_basic_simulation_config
from bluenaas.core.stimulation.utils import (
    add_single_synapse,
    get_stimulus_name,
    is_current_varying_simulation,
)

from bluenaas.domains.simulation import (
    RecordingLocation,
    SingleNeuronSimulationConfig,
    SimulationStreamData,
    WORKER_TASK_STATES,
)
from bluenaas.core.exceptions import SimulationError
from bluenaas.infrastructure.celery import celery_app
from bluenaas.infrastructure.celery.single_simulation_task_class import (
    SingleSimulationTask,
)
from bluenaas.utils.serializer import (
    deserialize_synapse_series_list,
)
from bluenaas.utils.util import diff_list
from bluenaas.infrastructure.redis import redis_client
from bluenaas.services.simulation.constants import SIMULATION_TIMEOUT_SECONDS

ERROR_STATE: WORKER_TASK_STATES = "FAILURE"
SIMULATION_SUCCESS: WORKER_TASK_STATES = "SUCCESS"


@celery_app.task(
    bind=True,
    serializer="json",
    base=SingleSimulationTask,
)
def single_simulation_runner(
    self,
    *,
    me_model_id: str,
    synapses: str | None,  # Serialized list of synapses
    # NOTE: this need to be passed to be able to recover it in the celery task definition
    # and use it to save the simulation result
    org_id: str,
    project_id: str,
    sim_resource_self: str | None,
    token: str,
    config: SingleNeuronSimulationConfig,
    amplitude: float,
    frequency: float,
    recording_location: RecordingLocation,
    injection_segment: float = 0.5,
    thres_perc=None,
    add_hypamp=True,
    realtime=False,
    autosave=False,
    channel_name: str,
):
    """
    NOTE: The simulation *needs* to run in a child process to allow the neuron simulator to be "reset" correctly.
    https://www.neuron.yale.edu/phpBB/viewtopic.php?t=4039

    If we don't run simulation in the child process then the simulator will return results for past simulation that were run in the worker also.
    """
    queue = billiard.Queue()
    process = billiard.Process(
        target=perform_sim,
        args=(
            queue,
            me_model_id,
            synapses,
            org_id,
            project_id,
            sim_resource_self,
            token,
            config,
            amplitude,
            frequency,
            recording_location,
            injection_segment,
            thres_perc,
            add_hypamp,
            realtime,
            autosave,
            channel_name,
        ),
    )

    process.start()

    try:
        task_result = queue.get(
            timeout=SIMULATION_TIMEOUT_SECONDS
        )  # If simulation process does not return in 15 minutes, abort the simulation.
        if task_result["state"] == ERROR_STATE:
            logger.debug(f"Received error state {task_result}")
            raise SimulationError(task_result["data"])
        if task_result["state"] == SIMULATION_SUCCESS:
            if not realtime or autosave is True:
                return task_result["data"]
            else:
                return None
    except QueueEmptyException:
        raise SimulationError(
            f"Received no message from child process in worker for {SIMULATION_TIMEOUT_SECONDS} seconds. simultion_resource: {sim_resource_self} channel_name: {channel_name}"
        )
    except SimulationError as ex:
        raise ex
    except Exception as ex:
        logger.exception(
            f"Exception in worker process for sim_resource {sim_resource_self} {ex}"
        )
        raise SimulationError from ex
    finally:
        logger.debug("Cleaning up the worker process")
        process.join()
        logger.debug("Cleaning done")


def perform_sim(
    queue: billiard.Queue,
    me_model_id: str,
    synapses: str | None,  # Serialized list of synapses
    # NOTE: this need to be passed to be able to recover it in the celery task definition
    # and use it to save the simulation result
    org_id: str,
    project_id: str,
    resource_self: str | None,
    token: str,
    config: str,  # string representing the json object of type SingleNeuronSimulationConfig
    amplitude: float,
    frequency: float,
    recording_location: str,  # string representing the json object of type RecordingLocation
    injection_segment: float,
    thres_perc: float | None,
    add_hypamp: bool,
    realtime: bool,
    autosave: bool,
    channel_name: str | None,
):
    try:
        cf = SingleNeuronSimulationConfig(**json.loads(config))
        rl = RecordingLocation(**json.loads(recording_location))

        logger.info(f"""
            [enable_realtime]: {realtime}
            [amplitude]: {amplitude}
            [frequency]: {frequency}
            [simulation recording_location]: {recording_location}
        """)

        (_, cell) = setup_basic_simulation_config(
            config=cf,
            injection_segment=injection_segment,
            recording_location=rl,
            experimental_setup=cf.conditions,
            amplitude=amplitude,
            add_hypamp=add_hypamp,
            me_model_id=me_model_id,
            token=token,
            thres_perc=thres_perc,
        )

        from bluecellulab.simulation.simulation import Simulation

        is_current_simulation = is_current_varying_simulation(cf)
        if synapses is not None:
            deserialized_synapses = deserialize_synapse_series_list(synapses)
            logger.debug(
                f"Running synaptome simulation with {len(deserialized_synapses)} synapses. Current varying {is_current_simulation}"
            )

            for synapse in deserialized_synapses:
                add_single_synapse(
                    cell=cell,
                    synapse=synapse,
                    experimental_setup=cf.conditions,
                )

        protocol = cf.current_injection.stimulus.stimulus_protocol
        stimulus_name = get_stimulus_name(protocol)

        sec, seg = cell.sections[rl.section], rl.offset

        cell_section = f"{rl.section}_{seg}"

        varying_key = stimulus_name.name if is_current_simulation else "frequency"
        varying_order = amplitude if is_current_simulation else frequency
        varying_type = "current" if is_current_simulation else "frequency"

        label = "{}_{}".format(
            varying_key,
            frequency if varying_type == "frequency" else amplitude,
        )

        prev_voltage = {}
        prev_time = {}
        final_result = {}

        def track_simulation_progress() -> None:
            logger.debug(
                f"PROGRESS. KEY {varying_key} TYPE {varying_type} ORDER {varying_order}"
            )
            voltage = cell.get_voltage_recording(sec, seg)
            time = cell.get_time()

            if realtime:
                if cell_section not in prev_voltage:
                    prev_voltage[cell_section] = np.array([])
                if cell_section not in prev_time:
                    prev_time[cell_section] = np.array([])

                time_diff = diff_list(prev_time[cell_section], time)
                voltage_diff = diff_list(prev_voltage[cell_section], voltage)

                prev_voltage[cell_section] = voltage
                prev_time[cell_section] = time

                partial_result: SimulationStreamData = {
                    "state": "PROGRESS",
                    "name": label,
                    "recording": cell_section,
                    "amplitude": amplitude,
                    "frequency": frequency,
                    "varying_key": varying_key,
                    "varying_type": varying_type,
                    "varying_order": varying_order,
                    "x": time_diff.tolist(),
                    "y": voltage_diff.tolist(),
                }
                redis_client.publish(channel_name, json.dumps(partial_result))
            return None

        simulation = Simulation(
            cell,
            custom_progress_function=track_simulation_progress if realtime else None,
        )

        simulation.run(
            maxtime=cf.duration,
            show_progress=realtime,
            dt=cf.conditions.time_step,
            cvode=False,
        )

        if realtime:
            assert channel_name is not None
            redis_client.publish(
                channel_name, json.dumps({"state": SIMULATION_SUCCESS})
            )

        # NOTE: return result to be able to recover it
        # 1. when there is no realtime
        # 2. the user enable autosaving
        voltage = cell.get_voltage_recording(sec, seg)
        time = cell.get_time()

        final_result = {
            "state": SIMULATION_SUCCESS,
            "name": label,
            "recording": cell_section,
            "amplitude": amplitude,
            "frequency": frequency,
            "varying_key": varying_key,
            "varying_type": varying_type,
            "varying_order": varying_order,
            "x": time.tolist(),
            "y": voltage.tolist(),
        }
        queue.put({"state": SIMULATION_SUCCESS, "data": final_result})

    except Exception as ex:
        logger.exception(
            f"Simulation error in celery worker {ex}. Channel name {channel_name}"
        )
        if realtime is True:
            assert channel_name is not None
            redis_client.publish(
                channel_name,
                json.dumps(
                    {
                        "state": "FAILURE",
                        "error": f"{ex}",
                    }
                ),
            )
        queue.put({"state": ERROR_STATE, "data": f"{ex}"})
