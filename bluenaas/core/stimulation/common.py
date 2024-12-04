from __future__ import annotations
import os
import queue as que
from loguru import logger
from collections import namedtuple
import numpy as np
from typing import Literal
from bluenaas.core.exceptions import ChildSimulationError
from bluenaas.core.model import model_factory
from bluenaas.domains.morphology import SynapseSeries
from bluenaas.domains.simulation import (
    CurrentInjectionConfig,
    ExperimentSetupConfig,
    RecordingLocation,
    SingleNeuronSimulationConfig,
)
from bluenaas.utils.const import (
    SUB_PROCESS_STOP_EVENT,
)
from bluenaas.utils.simulation import get_simulations_by_recoding_name
from bluenaas.utils.util import diff_list
from bluenaas.core.stimulation.utils import (
    get_stimulus_from_name,
    get_stimulus_name,
    init_process_worker,
)

DEFAULT_INJECTION_LOCATION = "soma[0]"

TaskArgs = namedtuple(
    "TaskArgs",
    [
        "template_params",
        "stimulus",
        "injection_section_name",
        "injection_segment",
        "recording_locations",
        "synapse_series",
        "conditions",
        "simulation_duration",
        "stimulus_name_or_frequency",
        "amplitude_or_additional_param",
        "add_hypamp",
        "enable_realtime",
        "queue",
    ],
)


def prepare_stimulation_parameters(
    cell,
    current_injection: CurrentInjectionConfig,
    recording_locations: list[RecordingLocation],
    frequency_to_synapse_series: dict[float, list[SynapseSeries]] | None,
    current_synapse_series: list[SynapseSeries] | None,
    conditions: ExperimentSetupConfig,
    simulation_duration: int,
    threshold_based: bool = False,
    injection_segment: float = 0.5,
    add_hypamp: bool = True,
    varying_type: Literal["frequency", "current"] = "current",
    enable_realtime: bool = True,
):
    from bluecellulab.stimulus.factory import StimulusFactory

    stim_factory = StimulusFactory(dt=1.0)
    task_args = []

    injection_section_name = (
        current_injection.inject_to
        if current_injection is not None and current_injection.inject_to is not None
        else DEFAULT_INJECTION_LOCATION
    )
    protocol = current_injection.stimulus.stimulus_protocol
    amplitudes = current_injection.stimulus.amplitudes
    stimulus_name = get_stimulus_name(protocol)

    assert current_injection is not None
    if varying_type == "frequency":
        # Prepare arguments for each frequency
        for frequency in frequency_to_synapse_series:
            if threshold_based:
                thres_perc = amplitudes
                amp = None
            else:
                thres_perc = None
                amp = amplitudes

            stimulus = get_stimulus_from_name(
                stimulus_name, stim_factory, cell, thres_perc, amp
            )

            task_args.append(
                TaskArgs(
                    cell.template_params,
                    stimulus,
                    injection_section_name,
                    injection_segment,
                    recording_locations,
                    frequency_to_synapse_series[frequency],
                    conditions,
                    simulation_duration,
                    amplitudes,
                    frequency,
                    add_hypamp,
                    enable_realtime,
                    None,
                )
            )
    elif varying_type == "current":
        for amplitude in amplitudes:
            if threshold_based:
                thres_perc = amplitude
                amp = None
            else:
                thres_perc = None
                amp = amplitude

            stimulus = get_stimulus_from_name(
                stimulus_name, stim_factory, cell, thres_perc, amp
            )

            task_args.append(
                TaskArgs(
                    cell.template_params,
                    stimulus,
                    injection_section_name,
                    injection_segment,
                    recording_locations,
                    current_synapse_series,
                    conditions,
                    simulation_duration,
                    stimulus_name,
                    amplitude,
                    add_hypamp,
                    enable_realtime,
                    None,
                )
            )

    return task_args


def basic_simulation_config(
    template_params,
    stimulus,
    injection_section_name: str,
    injection_segment: float,
    recording_locations: list[RecordingLocation],
    experimental_setup: ExperimentSetupConfig,
    add_hypamp: bool = True,
):
    import neuron
    from bluecellulab.cell.core import Cell
    from bluecellulab.stimulus.circuit_stimulus_definitions import Hyperpolarizing
    from bluecellulab.rngsettings import RNGSettings

    rng = RNGSettings(
        base_seed=experimental_setup.seed,
        synapse_seed=experimental_setup.seed,
        stimulus_seed=experimental_setup.seed,
    )

    rng.set_seeds(
        base_seed=experimental_setup.seed,
    )

    cell = Cell.from_template_parameters(template_params)
    injection_section = cell.sections[injection_section_name]

    for loc in recording_locations:
        sec, seg = cell.sections[loc.section], loc.offset

        cell.add_voltage_recording(
            section=sec,
            segx=seg,
        )
        iclamp, _ = cell.inject_current_waveform(
            stimulus.time,
            stimulus.current,
            section=injection_section,
            segx=injection_segment,
        )

    current_vector = neuron.h.Vector()
    current_vector.record(iclamp._ref_i)
    current = np.array(current_vector.to_python())
    neuron.h.v_init = experimental_setup.vinit
    neuron.h.celsius = experimental_setup.celsius

    if add_hypamp:
        hyp_stim = Hyperpolarizing(
            target="",
            delay=0.0,
            duration=stimulus.stimulus_time,
        )
        cell.add_replay_hypamp(hyp_stim)

    return cell, current


def dispatch_simulation_result(
    cell,
    queue,
    current,
    recording_locations: list[RecordingLocation],
    simulation_duration: int,
    time_step: int,
    amplitude: float | None,
    frequency: float | None,
    varying_type: Literal["frequency", "current"],
    varying_key: str,
    enable_realtime: bool,
):
    from bluecellulab.simulation.simulation import Simulation

    prev_voltage = {}
    prev_time = {}
    final_result = {}

    def process_simulation_recordings(enable_realtime=True):
        for loc in recording_locations:
            sec, seg = cell.sections[loc.section], loc.offset
            cell_section = f"{loc.section}_{seg}"
            label = f"{varying_key}_{frequency if varying_type == "frequency" else amplitude}"

            voltage = cell.get_voltage_recording(sec, seg)
            time = cell.get_time()

            if enable_realtime:
                if cell_section not in prev_voltage:
                    prev_voltage[cell_section] = np.array([])
                if cell_section not in prev_time:
                    prev_time[cell_section] = np.array([])

                time_diff = diff_list(prev_time[cell_section], time)
                voltage_diff = diff_list(prev_voltage[cell_section], voltage)

                prev_voltage[cell_section] = voltage
                prev_time[cell_section] = time

                queue.put(
                    {
                        "label": label,
                        "recording": cell_section,
                        "amplitude": amplitude,
                        "frequency": frequency,
                        "varying_key": frequency
                        if varying_key == "frequency"
                        else amplitude,
                        "t": time_diff.tolist(),
                        "v": voltage_diff.tolist(),
                    }
                )

            final_result[cell_section] = {
                "label": label,
                "recording_name": cell_section,
                "amplitude": amplitude,
                "frequency": frequency,
                "time": time.tolist(),
                "voltage": voltage.tolist(),
                "varying_key": varying_key,
            }

    try:
        simulation = Simulation(
            cell,
            custom_progress_function=process_simulation_recordings
            if enable_realtime
            else None,
        )

        simulation.run(
            maxtime=simulation_duration,
            show_progress=enable_realtime,
            dt=time_step,
            cvode=False,
        )

        process_simulation_recordings(enable_realtime)
        return final_result
    except Exception as ex:
        exception = ChildSimulationError(
            "child simulation failed {}".format(ex.__str__())
        )
        queue.put(exception)
        raise exception from ex
    finally:
        logger.info("child simulation complete")
        queue.put(SUB_PROCESS_STOP_EVENT)


def apply_multiple_simulations(args, runner):
    import billiard as brd
    from celery import current_task, states
    from celery.exceptions import Ignore
    from bluecellulab.simulation.neuron_globals import NeuronGlobals

    neuron_global_params = NeuronGlobals.get_instance().export_params()
    enable_realtime = all(arg.enable_realtime is True for arg in args)

    with brd.Manager() as manager:
        queue = manager.Queue()

        with brd.pool.Pool(
            processes=min(len(args), os.cpu_count() or len(args)),
            initializer=init_process_worker,
            initargs=(neuron_global_params,),
            maxtasksperchild=1,
        ) as pool:
            if enable_realtime is True:
                simulations = pool.starmap_async(
                    runner,
                    iterable=[arg._replace(queue=queue) for arg in args],
                )
            else:
                simulations = pool.starmap(
                    runner,
                    iterable=[arg._replace(queue=queue) for arg in args],
                )

            process_finished = 0
            while True and enable_realtime:
                try:
                    record = queue.get(timeout=1)
                    if isinstance(record, ChildSimulationError):
                        current_task.update_state(
                            state=states.FAILURE,
                            meta={
                                "result": None,
                                "exc_message": record.__str__(),
                                "exc_type": "ChildSimulationError",
                                "all_simulations_finished": False,
                            },
                        )
                    elif record != SUB_PROCESS_STOP_EVENT:
                        current_task.update_state(
                            state="PROGRESS",
                            meta={
                                "exc_type": None,
                                "exc_message": None,
                                "all_simulations_finished": False,
                                "result": {
                                    "hash": hash(
                                        "{}/{}/{}/{}/{}".format(
                                            record["recording"],
                                            record["amplitude"],
                                            record["frequency"],
                                            tuple(record["t"]),
                                            tuple(record["v"]),
                                        )
                                    ),
                                    **record,
                                },
                            },
                        )
                    else:
                        process_finished += 1
                        if process_finished == len(args):
                            current_task.update_state(
                                state=states.SUCCESS,
                                meta={
                                    "hash": "success",
                                    "result": None,
                                    "exc_type": None,
                                    "exc_message": None,
                                    "all_simulations_finished": True,
                                },
                            )
                            break
                except que.Empty:
                    continue
                except Exception as ex:
                    logger.exception(
                        f"Error during pulling simulation data from sub processes: {ex}"
                    )
                    current_task.update_state(
                        state=states.FAILURE,
                        meta={
                            "hash": "failure",
                            "result": None,
                            "exc_message": ex.__str__(),
                            "exc_type": type(ex).__name__,
                            "all_simulations_finished": False,
                        },
                    )
                    raise Ignore()

            return get_simulations_by_recoding_name(
                simulations=simulations.get() if enable_realtime else simulations,
            )


def setup_basic_simulation_config(
    config: SingleNeuronSimulationConfig,
    injection_segment: float,
    recording_location: RecordingLocation,
    experimental_setup: ExperimentSetupConfig,
    amplitude: float,
    add_hypamp: bool = True,
    thres_perc: float = None,
    me_model_id: str = None,
    token: str | None = None,
):
    model = model_factory(
        model_self=me_model_id,
        hyamp=config.conditions.hypamp,
        bearer_token=token,
    )

    from bluecellulab.simulation.neuron_globals import NeuronGlobals
    from bluecellulab.stimulus.circuit_stimulus_definitions import Hyperpolarizing
    from bluecellulab.rngsettings import RNGSettings
    from bluecellulab.stimulus.factory import StimulusFactory
    from bluecellulab.importer import neuron

    neuron_global_params = NeuronGlobals.get_instance().export_params()
    NeuronGlobals.get_instance().load_params(neuron_global_params)

    injection_section_name = config.current_injection.inject_to

    rng = RNGSettings(
        base_seed=experimental_setup.seed,
        synapse_seed=experimental_setup.seed,
        stimulus_seed=experimental_setup.seed,
    )

    rng.set_seeds(
        base_seed=experimental_setup.seed,
    )
    # from bluecellulab.importer import neuron
    cell = model.CELL._cell
    injection_section = cell.sections[injection_section_name]

    sec, seg = cell.sections[recording_location.section], recording_location.offset

    cell.add_voltage_recording(
        section=sec,
        segx=seg,
    )

    protocol = config.current_injection.stimulus.stimulus_protocol
    stimulus_name = get_stimulus_name(protocol)
    stim_factory = StimulusFactory(dt=1.0)
    stimulus = get_stimulus_from_name(
        stimulus_name,
        stim_factory,
        cell,
        thres_perc,
        amplitude,
    )

    iclamp, _ = cell.inject_current_waveform(
        stimulus.time,
        stimulus.current,
        section=injection_section,
        segx=injection_segment,
    )

    current_vector = neuron.h.Vector()
    current_vector.record(iclamp._ref_i)
    current = np.array(current_vector.to_python())
    neuron.h.v_init = experimental_setup.vinit
    neuron.h.celsius = experimental_setup.celsius

    if add_hypamp:
        hyp_stim = Hyperpolarizing(
            target="",
            delay=0.0,
            duration=stimulus.stimulus_time,
        )
        cell.add_replay_hypamp(hyp_stim)

    return (current, cell)
