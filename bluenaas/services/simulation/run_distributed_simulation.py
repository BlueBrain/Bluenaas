import json
from multiprocessing.pool import AsyncResult
from urllib.parse import quote_plus
from celery import states
from loguru import logger
from http import HTTPStatus as status

from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode
from bluenaas.core.stimulation.utils import is_current_varying_simulation
from bluenaas.domains.nexus import FullNexusSimulationResource
from bluenaas.domains.simulation import (
    SimulationEvent,
    SingleNeuronSimulationConfig,
)
from bluenaas.infrastructure.celery.tasks.single_simulation_runner import (
    single_simulation_runner,
)
from bluenaas.infrastructure.celery.tasks.initiate_simulation import initiate_simulation
from bluenaas.services.simulation.prepare_simulation_resource import (
    prepare_simulation_resources,
)
from bluenaas.utils.streaming import StreamingResponseWithCleanup, cleanup_worker
from bluenaas.utils.serializer import deserialize_synapse_series_dict
from bluenaas.utils.simulation import convert_to_simulation_response
from bluenaas.utils.hash_obj import get_hash


task_state_descriptions = {
    "INIT": "Simulation is captured by the system",
    "PROGRESS": "Simulation is currently in progress.",
    "PENDING": "Simulation is waiting for execution.",
    "STARTED": "Simulation has started executing.",
    "SUCCESS": "The simulation completed successfully.",
    "FAILURE": "The simulation has failed.",
    "REVOKED": "The simulation has been canceled.",
    "PARTIAL_SUCCESS": "The simulation has been completed but not fully successful.",
}


def get_event_from_task_state(state) -> SimulationEvent:
    """
    Get the event type based on the task state.
    """
    if state in (states.PENDING, states.SUCCESS):
        event = "info"
    elif state == "PROGRESS":
        event = "data"
    elif state == states.FAILURE:
        event = "error"
    else:
        event = "info"

    return event.lower()


def build_stream_obj(task: AsyncResult, job_id: str):
    return f"{json.dumps(
            {
                "event": get_event_from_task_state(task.state),
                "description": task_state_descriptions[task.state],
                "state": task.state.lower(),
                "task_id": task.id,
                "job_id": job_id,
                "data": task.result or None,
            }
        )}\n"


def run_distributed_simulation(
    org_id: str,
    project_id: str,
    model_self: str,
    token: str,
    config: SingleNeuronSimulationConfig,
    autosave: bool = False,
    realtime: bool = False,
):
    from celery import group

    amplitudes = config.current_injection.stimulus.amplitudes
    simulation_instances = []
    simulation_resource = None

    if autosave:
        (
            me_model_self,
            synaptome_model_self,
            _,
            _,
            simulation_resource,
        ) = prepare_simulation_resources(
            token,
            model_self,
            org_id,
            project_id,
            SingleNeuronSimulationConfig.model_validate(config),
            status="started",
        )

    try:
        # NOTE: build the model and calculate synapses series (current/frequency)
        # this should be ran before the sub simulation
        # Reason: to get the frequency synapses series (it required to know how many parallel simulation should be run)
        # chaining tasks is not an option here using (chain from celery or "|")
        prep_job = initiate_simulation.apply_async(
            kwargs={
                "model_self": model_self,
                "token": token,
                "config": config.model_dump_json(),
            }
        )

        model_info = prep_job.get()
        # NOTE: used to calculate how many sub-simulation we should spin up (for frequency varying)
        (_, _, _, frequency_to_synapse_config) = model_info

        is_current_simulation = is_current_varying_simulation(config)
        resource_self = (
            simulation_resource["_self"] if simulation_resource is not None else None
        )

        # TODO: better handling of this condition/loop to generate simulation tasks list
        if is_current_simulation:
            for amplitude in amplitudes:
                for recording_location in config.record_from:
                    simulation_instances.append(
                        single_simulation_runner.s(
                            model_info,
                            org_id=org_id,
                            project_id=project_id,
                            resource_self=resource_self,
                            token=token,
                            config=config.model_dump_json(),
                            amplitude=amplitude,
                            frequency=None,
                            recording_location=recording_location.model_dump_json(),
                            injection_segment=0.5,
                            thres_perc=None,
                            add_hypamp=True,
                            realtime=realtime,
                            autosave=autosave,
                        )
                    )

        else:
            for frequency in deserialize_synapse_series_dict(
                frequency_to_synapse_config
            ):
                amplitudes = config.current_injection.stimulus.amplitudes

                # NOTE: frequency simulation should have only one amplitude (for the moment)
                # TODO: capture the assertion exception
                assert isinstance(amplitudes, float)

                for recording_location in config.record_from:
                    simulation_instances.append(
                        single_simulation_runner.s(
                            model_info,
                            org_id=org_id,
                            project_id=project_id,
                            resource_self=resource_self,
                            token=token,
                            config=config.model_dump_json(),
                            amplitude=amplitudes,
                            frequency=frequency,
                            recording_location=recording_location.model_dump_json(),
                            injection_segment=0.5,
                            thres_perc=None,
                            add_hypamp=True,
                            realtime=realtime,
                            autosave=autosave,
                        )
                    )

        grouped_tasks = group(simulation_instances)
        job = grouped_tasks.apply_async()

        # NOTE: if both `realtime` and `autosave` are enabled
        # the simulation will be streamed but the autosave will be handled in the celery task definition
        # please check: bluenaas/infrastructure/celery/single_simulation_task_class.py
        if realtime:
            hash_list = []

            def streamify():
                try:
                    # NOTE: first stream chunk is useful in different client to be able to get the job_id
                    # benefit: shutdown the simulation
                    yield f"{json.dumps(
                        {
                            "event": "init",
                            "description": task_state_descriptions["INIT"],
                            "state": "captured",
                            "job_id": job.id,
                            "resource_self": resource_self, 
                            "data": None,
                        }
                    )}\n"

                    while not job.ready():
                        for v in job.results:
                            # NOTE: celery keep streaming the same state if there is no new state in the backend
                            # NOTE: to be able to reduce streaming to the client and also protect the client from the overloaded response
                            # NOTE: we should calculate the hash of different chunks and stream only it not streamed yet
                            hash = get_hash(v.result)
                            if hash not in hash_list:
                                hash_list.append(hash)
                                yield build_stream_obj(v, job.id)

                    status = None
                    if job.successful():
                        status = states.SUCCESS
                    elif (job.completed_count() > 0) and (
                        job.completed_count() < len(job.results)
                    ):
                        # NOTE: this is new state introduced if we want to be more precise about the quality of the results
                        status = "PARTIAL_SUCCESS"
                    else:
                        status = states.FAILURE
                    # TODO: check for the revoked task status
                    description = task_state_descriptions[status]

                    # NOTE: finally stream the latest status of the simulation
                    yield f"{json.dumps(
                        {
                            "event": "info",
                            "description":description,
                            "state": status,
                            "job_id": job.id,
                            "resource_self": resource_self, 
                            "data": None,
                        }
                    )}\n"

                except Exception as ex:
                    logger.info(f"Exception in task streaming: {ex}")
                    raise Exception("Trouble while streaming simulation data")

            return StreamingResponseWithCleanup(
                streamify(),
                finalizer=lambda: cleanup_worker(
                    job.id,
                ),
                media_type="application/octet-stream",
                headers={
                    "x-bnaas-job": job.id,
                },
            )

        elif autosave:
            # NOTE: if autosave simulation is enabled then return the simulation with
            # 1- job_id to be able to shutdown the simulation
            # 2- query nexus for the simulation (status and result) at any time
            return convert_to_simulation_response(
                job_id=job.id,
                simulation_uri=quote_plus(simulation_resource["@id"]),
                simulation_resource=FullNexusSimulationResource.model_validate(
                    simulation_resource,
                ),
                me_model_self=me_model_self,
                synaptome_model_self=synaptome_model_self,
                distribution=None,
            )

    except Exception as ex:
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Error while running simulation",
            details=ex.__str__(),
        ) from ex
