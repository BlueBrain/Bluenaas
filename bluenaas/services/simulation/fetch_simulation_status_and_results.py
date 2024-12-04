from http import HTTPStatus

from bluenaas.domains.nexus import FullNexusSimulationResource
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.simulation import SimulationDetailsResponse
from urllib.parse import unquote
from loguru import logger
from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode
from bluenaas.utils.simulation import (
    get_simulation_type,
    convert_to_simulation_response,
)


def fetch_simulation_status_and_results(
    token: str, org_id: str, project_id: str, simulation_uri: str
) -> SimulationDetailsResponse:
    try:
        simulation_id = unquote(simulation_uri)
        nexus_helper = Nexus(
            {"token": token, "model_self_url": simulation_id}
        )  # TODO: Remove model_id as a required field for nexus helper

        simulation_resource = nexus_helper.fetch_resource_for_org_project(
            org_label=org_id, project_label=project_id, resource_id=simulation_id
        )

        if simulation_resource.get("_deprecated"):
            raise BlueNaasError(
                http_status_code=HTTPStatus.NOT_FOUND,
                error_code=BlueNaasErrorCode.NEXUS_ERROR,
                message="Deleted simulation cannot be retrieved",
            )
        valid_simulation = FullNexusSimulationResource.model_validate(
            simulation_resource
        )
        sim_type = get_simulation_type(
            simulation_resource=valid_simulation,
        )

        used_model_id = valid_simulation.used.get("@id")
        if sim_type == "single-neuron-simulation":
            me_model_self = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id, project_label=project_id, resource_id=used_model_id
            )["_self"]
            synaptome_model_self = None
        else:
            synaptome_model = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id,
                project_label=project_id,
                resource_id=used_model_id,
            )
            synaptome_model_self = synaptome_model["_self"]
            me_model = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id,
                project_label=project_id,
                resource_id=synaptome_model["used"]["@id"],
            )
            me_model_self = me_model["_self"]

        file_url = simulation_resource["distribution"]["contentUrl"]
        file_response = nexus_helper.fetch_file_by_url(file_url)
        distribution = file_response.json()

        if valid_simulation.status != "success":
            assert "simulation" in distribution
        return convert_to_simulation_response(
            simulation_uri=simulation_resource["@id"],
            job_id=None,
            simulation_resource=valid_simulation,
            me_model_self=me_model_self,
            synaptome_model_self=synaptome_model_self,
            simulation_config=distribution["config"],
            results=distribution["simulation"]
            if "simulation" in distribution
            else None,
        )

    except Exception as ex:
        logger.exception(f"Error fetching simulation results {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            message="retrieving simulation data failed",
            details=ex.__str__(),
        ) from ex
