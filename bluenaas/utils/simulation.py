from typing import Optional, cast
from urllib.parse import quote_plus
from celery import states  # type: ignore
import json
from loguru import logger

from bluenaas.core.exceptions import BlueNaasErrorCode
from bluenaas.services.simulation.constants import (
    task_state_descriptions,
)
from bluenaas.domains.nexus import (
    FullNexusSimulationResource,
    NexusBaseResource,
)
from bluenaas.domains.simulation import (
    SimulationType,
    SimulationEvent,
    SimulationStreamData,
    SimulationErrorMessage,
    NexusSimulationType,
    SimulationDetailsResponse,
    SIMULATION_TYPE_MAP,
    SingleNeuronSimulationConfig,
    BrainRegion,
)


def get_simulation_type(
    simulation_resource: NexusBaseResource,
) -> SimulationType:
    nexus_sim_type: str | None
    if isinstance(simulation_resource.type, list):
        nexus_sim_type = [
            res_type
            for res_type in simulation_resource.type
            if res_type == "SingleNeuronSimulation" or res_type == "SynaptomeSimulation"
        ][0]
    else:
        nexus_sim_type = simulation_resource.type

    if nexus_sim_type in SIMULATION_TYPE_MAP:
        return SIMULATION_TYPE_MAP[cast(NexusSimulationType, nexus_sim_type)]
    else:
        raise ValueError(f"Unsupported simulation type {nexus_sim_type}")


def get_nexus_simulation_type(sim_type: SimulationType) -> NexusSimulationType:
    sim_types_to_nexus_types = {v: k for k, v in SIMULATION_TYPE_MAP.items()}
    if sim_type in sim_types_to_nexus_types:
        return sim_types_to_nexus_types[sim_type]
    else:
        raise ValueError(f"Unsupported simulation type {sim_type}")


def convert_to_simulation_response(
    job_id: str | None,
    simulation_uri: str,
    simulation_resource: FullNexusSimulationResource,
    me_model_self: str,
    synaptome_model_self: Optional[str],
    simulation_config: Optional[SingleNeuronSimulationConfig],
    results: Optional[dict],
):
    brain_region = simulation_resource.brainLocation.get("brainRegion")
    return SimulationDetailsResponse(
        # Main info
        id=quote_plus(simulation_uri),
        job_id=job_id,
        status=simulation_resource.status,
        results=results,
        error=simulation_resource.error,
        # Simulation metadata
        type=get_simulation_type(simulation_resource),
        name=simulation_resource.name,
        description=simulation_resource.description,
        created_by=simulation_resource.createdBy,
        created_at=simulation_resource.createdAt,
        injection_location=simulation_resource.injectionLocation,
        recording_location=simulation_resource.recordingLocation,
        brain_region=BrainRegion(id=brain_region["@id"], label=brain_region["label"]),
        config=simulation_config,
        # Used model details
        me_model_id=me_model_self,
        synaptome_model_id=synaptome_model_self,
    )


def get_simulations_by_recoding_name(simulations: list) -> dict[str, list]:
    record_location_to_simulation_result: dict[str, list] = {}

    # Iterate over simulation result for each current/frequency
    for trace in simulations:
        # For a given current/frequency, gather data for different recording locations
        for recording_name in trace:
            if recording_name not in record_location_to_simulation_result:
                record_location_to_simulation_result[recording_name] = []

            record_location_to_simulation_result[recording_name].append(
                {
                    "label": trace[recording_name]["label"],
                    "amplitude": trace[recording_name]["amplitude"],
                    "frequency": trace[recording_name]["frequency"],
                    "recording": trace[recording_name]["recording_name"],
                    "varying_key": trace[recording_name]["varying_key"],
                    "type": "scatter",
                    "t": trace[recording_name]["time"],
                    "v": trace[recording_name]["voltage"],
                }
            )

    return record_location_to_simulation_result


def get_event_from_task_state(state) -> SimulationEvent:
    """
    Get the event type based on the task state.
    """
    event: SimulationEvent = "info"
    if state in (states.PENDING, states.SUCCESS):
        event = "info"
    elif state == "PROGRESS":
        event = "data"
    elif state == states.FAILURE:
        event = "error"
    else:
        event = "info"

    return event


def build_stream_obj(task_result: SimulationStreamData, job_id: str):
    return f"{json.dumps(
            {
                "event": get_event_from_task_state(task_result['state']),
                "description": task_state_descriptions[task_result['state']],
                "state": task_result['state'].lower(),
                # TODO: Add task id
                # "task_id": task.id,
                "job_id": job_id,
                "data": task_result,
            }
        )}\n"


def build_stream_error(error_result: SimulationErrorMessage | None, job_id: str):
    error_details = (
        error_result["error"]
        if error_result is not None and "error" in error_result
        else "Unknown simulation error"
    )

    return f"{json.dumps(
        {
            "event": "error",
            "description": task_state_descriptions["FAILURE"],
            "state": "failure",
            "job_id": job_id, 
            "data": {                          
                "error_code": BlueNaasErrorCode.SIMULATION_ERROR,
                "message": "Simulation failed",
                "details": error_details
            }
        }
        )}\n"


def celery_result_to_nexus_distribution_result(celery_result: SimulationStreamData):
    try:
        return {
            "name": celery_result["name"],
            "recording": celery_result["recording"],
            "amplitude": celery_result["amplitude"],
            "frequency": celery_result["frequency"]
            if "frequency" in celery_result
            else None,
            "varying_key": celery_result["varying_key"],
            "varying_order": celery_result["varying_order"],
            "varying_type": celery_result["varying_type"],
            "x": celery_result["x"],
            "y": celery_result["y"],
        }
    except Exception as ex:
        logger.exception(
            f"Error while converting celery task result to nexus distribution item {ex}"
        )
