from typing import Optional
from urllib.parse import unquote


from bluenaas.domains.nexus import (
    BaseNexusSimulationResource,
    FullNexusSimulationResource,
)
from bluenaas.domains.simulation import (
    SimulationType,
    NexusSimulationType,
    SimulationResultItemResponse,
    SIMULATION_TYPE_MAP,
)


def get_simulation_type(
    simulation_resource: BaseNexusSimulationResource,
) -> SimulationType:
    if isinstance(simulation_resource.type, list):
        nexus_sim_type = [
            res_type
            for res_type in simulation_resource.type
            if res_type == "SingleNeuronSimulation" or res_type == "SynaptomeSimulation"
        ][0]
    else:
        nexus_sim_type = simulation_resource.type

    if nexus_sim_type in SIMULATION_TYPE_MAP:
        return SIMULATION_TYPE_MAP[nexus_sim_type]
    else:
        raise ValueError(f"Unsupported simulation type {nexus_sim_type}")


def get_nexus_simulation_type(sim_type: SimulationType) -> NexusSimulationType:
    sim_types_to_nexus_types = {v: k for k, v in SIMULATION_TYPE_MAP.items()}
    if sim_type in sim_types_to_nexus_types:
        return sim_types_to_nexus_types[sim_type]
    else:
        raise ValueError(f"Unsupported simulation type {sim_type}")


def convert_to_simulation_response(
    job_id: str,
    simulation_uri: str,
    simulation_resource: FullNexusSimulationResource,
    me_model_self: str,
    synaptome_model_self: Optional[str],
    distribution: Optional[dict],
):
    return SimulationResultItemResponse(
        id=unquote(simulation_uri),
        job_id=job_id,
        self_uri=simulation_resource.self,
        name=simulation_resource.name,
        description=simulation_resource.description,
        type=get_simulation_type(simulation_resource),
        status=simulation_resource.status,
        created_by=simulation_resource.createdBy,
        created_at=simulation_resource.createdAt,
        results=distribution and distribution.get("simulation", None),
        injection_location=simulation_resource.injectionLocation,
        recording_location=simulation_resource.recordingLocation,
        brain_location={
            "@type": simulation_resource.brainLocation.get("@type"),
            "brain_region": simulation_resource.brainLocation.get("brainRegion"),
        },
        config=distribution and distribution.get("config", None),
        me_model_self=me_model_self,
        synaptome_model_self=synaptome_model_self,
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
