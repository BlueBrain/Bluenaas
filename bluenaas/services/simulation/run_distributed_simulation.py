import json
from celery import states  # type: ignore
from celery.result import GroupResult  # type: ignore
from loguru import logger
from http import HTTPStatus as status
from uuid import uuid4
import time
from typing import NamedTuple, cast
from celery import group
from fastapi import BackgroundTasks

from bluenaas.external.nexus.nexus import Nexus
from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode
from bluenaas.core.stimulation.utils import is_current_varying_simulation
from bluenaas.domains.nexus import FullNexusSimulationResource
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    SimulationStreamData,
    SimulationStatus,
)
from bluenaas.services.simulation.constants import (
    task_state_descriptions,
    MESSAGE_WAIT_TIME_SECONDS,
    POLLING_INTERVAL_SECONDS,
    SIMULATION_TIMEOUT_SECONDS,
)
from bluenaas.infrastructure.celery.tasks.single_simulation_runner import (
    single_simulation_runner,
)
from bluenaas.infrastructure.celery.tasks.initiate_simulation import (
    initiate_simulation,
)
from bluenaas.services.simulation.setup_simulation_resource import (
    setup_simulation_resources,
)
from bluenaas.utils.streaming import StreamingResponseWithCleanup, cleanup_worker
from bluenaas.utils.serializer import (
    deserialize_synapse_series_dict,
    serialize_synapse_series_list,
)
from bluenaas.utils.simulation import (
    convert_to_simulation_response,
    build_stream_obj,
    build_stream_error,
    celery_result_to_nexus_distribution_result,
)
from bluenaas.infrastructure.redis import redis_client


class SerializedSimulationTaskArgs(NamedTuple):
    me_model_id: str
    synapses: str | None
    org_id: str
    project_id: str
    token: str
    config: str
    amplitude: float
    frequency: float | None
    recording_location: str
    injection_segment: float
    thres_perc: float | None
    add_hypamp: bool
    realtime: bool
    autosave: bool
    channel_name: str | None
    sim_resource_self: str | None


def get_base_task_arguments(
    sim_config: SingleNeuronSimulationConfig,
    serialized_current_synapses: str | None,
    serialized_frequency_synapses: str | None,
    me_model_id: str,
    token: str,
    org_id: str,
    project_id: str,
    realtime: bool,
    autosave: bool,
) -> list[SerializedSimulationTaskArgs]:
    is_current_simulation = is_current_varying_simulation(sim_config)
    task_args: list[SerializedSimulationTaskArgs] = []
    amplitudes = sim_config.current_injection.stimulus.amplitudes

    # TODO: better handling of this condition/loop to generate simulation tasks list
    if is_current_simulation:
        assert isinstance(amplitudes, list)
        for amplitude in amplitudes:
            for recording_location in sim_config.record_from:
                task_args.append(
                    SerializedSimulationTaskArgs(
                        me_model_id=me_model_id,
                        synapses=serialized_current_synapses,
                        org_id=org_id,
                        project_id=project_id,
                        sim_resource_self=None,
                        token=token,
                        config=sim_config.model_dump_json(),
                        amplitude=amplitude,
                        frequency=None,
                        recording_location=recording_location.model_dump_json(),
                        injection_segment=0.5,
                        thres_perc=None,
                        add_hypamp=True,
                        realtime=realtime,
                        autosave=autosave,
                        channel_name=None,
                    )
                )
    else:
        assert serialized_frequency_synapses is not None
        synapses_by_frequency = deserialize_synapse_series_dict(
            serialized_frequency_synapses
        )
        for frequency in synapses_by_frequency:
            # NOTE: frequency simulation should have only one amplitude (for the moment)
            assert isinstance(amplitudes, float)

            for recording_location in sim_config.record_from:
                task_args.append(
                    SerializedSimulationTaskArgs(
                        me_model_id=me_model_id,
                        synapses=serialize_synapse_series_list(
                            synapses_by_frequency[frequency]
                        ),
                        org_id=org_id,
                        project_id=project_id,
                        sim_resource_self=None,
                        token=token,
                        config=sim_config.model_dump_json(),
                        amplitude=amplitudes,
                        frequency=frequency,
                        recording_location=recording_location.model_dump_json(),
                        injection_segment=0.5,
                        thres_perc=None,
                        add_hypamp=True,
                        realtime=realtime,
                        autosave=autosave,
                        channel_name=None,
                    )
                )
    return task_args


def prepare_tasks_for_job(
    task_args: list[SerializedSimulationTaskArgs],
    channel_name: str,
    sim_resource_self: str | None,
):
    tasks = []

    for task_arg in task_args:
        if task_arg.autosave is True:
            assert sim_resource_self is not None
        tasks.append(
            single_simulation_runner.s(
                me_model_id=task_arg.me_model_id,
                synapses=task_arg.synapses,
                org_id=task_arg.org_id,
                project_id=task_arg.project_id,
                sim_resource_self=sim_resource_self,
                token=task_arg.token,
                config=task_arg.config,
                amplitude=task_arg.amplitude,
                frequency=task_arg.frequency,
                recording_location=task_arg.recording_location,
                injection_segment=task_arg.injection_segment,
                thres_perc=task_arg.thres_perc,
                add_hypamp=task_arg.add_hypamp,
                realtime=task_arg.realtime,
                autosave=task_arg.autosave,
                channel_name=channel_name if task_arg.realtime is True else None,
            )
        )
    return tasks


def run_distributed_simulation(
    org_id: str,
    project_id: str,
    model_self: str,
    token: str,
    config: SingleNeuronSimulationConfig,
    background_tasks: BackgroundTasks,
    autosave: bool = False,
    realtime: bool = False,
):
    if autosave is False and realtime is False:
        raise BlueNaasError(
            http_status_code=status.UNPROCESSABLE_ENTITY,
            error_code=BlueNaasErrorCode.SIMULATION_ERROR,
            message="Disabling autosave is not allowed for non-realtime simulations.",
        )

    try:
        # Get synapse metadata for cell. This is later used to determine the number of sub-simulation tasks needed
        prep_job = initiate_simulation.apply_async(
            kwargs={
                "model_self": model_self,
                "token": token,
                "config": config.model_dump_json(),
                "stimulation_config": config.current_injection.stimulus.model_dump_json(),
            }
        )
        prep_job_result = prep_job.get()
        (
            me_model_id,
            template_params,
            current_synapses,
            frequency_synapses,
            stimulus_plot_data,
        ) = prep_job_result

        task_args = get_base_task_arguments(
            sim_config=config,
            serialized_current_synapses=current_synapses,
            serialized_frequency_synapses=frequency_synapses,
            me_model_id=me_model_id,
            token=token,
            org_id=org_id,
            project_id=project_id,
            realtime=realtime,
            autosave=autosave,
        )

        simulation_resource = None
        if autosave:
            assert stimulus_plot_data is not None
            (
                me_model_self,
                synaptome_model_self,
                _,
                simulation_resource,
            ) = setup_simulation_resources(
                token=token,
                model_self=model_self,
                org_id=org_id,
                project_id=project_id,
                config=config,
                stimulus_plot_data=json.loads(stimulus_plot_data),
            )

        sim_resource_self = (
            simulation_resource["_self"] if simulation_resource is not None else None
        )
        channel_name = f"simulation_{uuid4()}"

        tasks = prepare_tasks_for_job(
            task_args=task_args,
            channel_name=channel_name,
            sim_resource_self=sim_resource_self,
        )
        assert len(task_args) == len(tasks)

        grouped_tasks = group(tasks)
        job = grouped_tasks.apply_async()

        if realtime:
            pubsub = redis_client.pubsub()
            pubsub.subscribe(channel_name)

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
                            "resource_self": sim_resource_self, 
                            "data": None,
                        }
                    )}\n"

                    # successful_message_count might not always be equal to the count of celery tasks that have successfully finished
                    # because there might be a time difference between when we receive the successful message from redis queue and when celery succesfully registers
                    # the task as complete.
                    successful_message_count = 0

                    while True:
                        message = pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=MESSAGE_WAIT_TIME_SECONDS,
                        )
                        if job.failed():
                            logger.debug(
                                f"Job {job.id} failed without publishing result for {MESSAGE_WAIT_TIME_SECONDS} seconds"
                            )
                            yield build_stream_error(None, job.id)
                            break

                        if message is not None:
                            message_data = json.loads(message["data"])

                            if message_data["state"] == "SUCCESS":
                                successful_message_count = successful_message_count + 1
                                logger.debug(
                                    f"Received {successful_message_count} shutdown events for {job.id}"
                                )
                                if successful_message_count == len(tasks):
                                    logger.debug(f"Received all results for {job.id}")
                                    break

                            elif message_data["state"] == "FAILURE":
                                logger.debug(
                                    f"Received failure message for job {job.id} {message_data}"
                                )
                                yield build_stream_error(message_data, job.id)
                                break

                            else:
                                yield build_stream_obj(message_data, job.id)
                        time.sleep(
                            POLLING_INTERVAL_SECONDS
                        )  # Do not continuously poll the queue to allow server to attend to other tasks.

                    status = None
                    if successful_message_count == len(tasks):
                        logger.debug("JOB SUCCESSFUL")
                        status = states.SUCCESS
                    elif (
                        successful_message_count < len(tasks)
                        and successful_message_count > 0
                    ):
                        # NOTE: this is new state introduced if we want to be more precise about the quality of the results
                        logger.debug(
                            f"Job partially successful. {successful_message_count} / {len(tasks)} completed"
                        )
                        status = "PARTIAL_SUCCESS"
                    else:
                        logger.debug(
                            f"JOB FAILED. Completed Tasks {successful_message_count}"
                        )
                        status = states.FAILURE

                    # TODO: check for the revoked task status
                    description = task_state_descriptions[status]

                    # finally stream the latest status of the simulation
                    yield f"{json.dumps(
                        {
                            "event": "info",
                            "description":description,
                            "state": status,
                            "job_id": job.id,
                            "resource_self": sim_resource_self, 
                            "data": None,
                        }
                    )}\n"

                except Exception as ex:
                    logger.info(f"Exception in task streaming: {ex}")
                    raise Exception("Trouble while streaming simulation data")
                finally:
                    logger.exception(f"Closing channel {channel_name}")
                    pubsub.unsubscribe(channel_name)
                    pubsub.close()

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

        else:
            assert simulation_resource is not None
            background_tasks.add_task(
                bg_task_process_simulation_results,
                celery_job=job,
                token=token,
                org_id=org_id,
                project_id=project_id,
                simulation_resource_self=simulation_resource["_self"],
            )
            return convert_to_simulation_response(
                job_id=job.id,
                simulation_uri=simulation_resource["@id"],
                simulation_resource=FullNexusSimulationResource.model_validate(
                    simulation_resource,
                ),
                me_model_self=me_model_self,
                synaptome_model_self=synaptome_model_self,
                simulation_config=config,
                results=None,
            )

    except Exception as ex:
        logger.exception(f"Error while running simulation {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Error while running simulation",
            details=ex.__str__(),
        ) from ex


def bg_task_process_simulation_results(
    celery_job: GroupResult,
    token: str,
    org_id: str,
    project_id: str,
    simulation_resource_self: str,
):
    try:
        # Collect results from celery worker
        logger.debug(f"Bg task started for simulation {simulation_resource_self}")
        task_results = celery_job.join_native(
            timeout=SIMULATION_TIMEOUT_SECONDS,
            interval=1,
            propagate=False,  # If one of the tasks failed, allow processing other tasks.
        )
        logger.debug(
            f"{len(task_results)} task Results gathered for simulation {simulation_resource_self}"
        )

        # Transform result into a dictionary
        final_result: dict[str, list[SimulationStreamData]] = {}
        failed_results = 0
        error_message = None
        for task_result in cast(list[SimulationStreamData], task_results):
            if isinstance(task_result, Exception):
                failed_results = failed_results + 1
                error_message = f"{task_result}"
                continue
            recording_name = task_result["recording"]

            final_result[recording_name] = (
                final_result[recording_name] if recording_name in final_result else []
            )
            final_result[recording_name].append(
                celery_result_to_nexus_distribution_result(task_result)
            )

        # Save result into nexus
        nexus_helper = Nexus({"token": token, "model_self_url": "model_id"})

        simulation_state: SimulationStatus
        if failed_results == 0:
            simulation_state = "success"
        elif failed_results == len(task_results):
            simulation_state = "failure"
        else:
            simulation_state = "partial_success"

        nexus_helper.update_simulation_with_final_results(
            simulation_resource_self=simulation_resource_self,
            org_id=org_id,
            project_id=project_id,
            status=simulation_state,
            results=final_result,
            error_message=error_message,
        )

        logger.debug(f"Simulation result saved for {simulation_resource_self}")
    except Exception as ex:
        logger.exception(f"Exception in non-realtime simulation {ex}")
    finally:
        logger.debug(f"Bg task completed for simulation {simulation_resource_self}")
