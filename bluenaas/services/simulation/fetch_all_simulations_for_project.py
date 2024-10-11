from http import HTTPStatus
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.simulation import SimulationStatusResponse
from urllib.parse import unquote
from loguru import logger
from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode
from bluenaas.utils.simulation import get_simulation_type, to_simulation_response


def fetch_simulation_status_and_results(
    token: str, org_id: str, project_id: str, encoded_simulation_id: str
) -> SimulationStatusResponse:
    try:
        simulation_id = unquote(encoded_simulation_id)
        nexus_helper = Nexus(
            {"token": token, "model_self_url": simulation_id}
        )  # TODO: Remove model_id as a required field for nexus helper

        simulation_resource = nexus_helper.fetch_resource_for_org_project(
            org_label=org_id, project_label=project_id, resource_id=simulation_id
        )
        sim_type = get_simulation_type(simulation_resource)

        used_model_id = simulation_resource["used"]["@id"]
        if sim_type == "single-neuron-simulation":
            me_model_self = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id, project_label=project_id, resource_id=used_model_id
            )["_self"]
            synaptome_model_self = None
        else:
            synaptome_model = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id, project_label=project_id, resource_id=used_model_id
            )
            synaptome_model_self = synaptome_model["_self"]
            me_model = nexus_helper.fetch_resource_for_org_project(
                org_label=org_id,
                project_label=project_id,
                resource_id=synaptome_model["used"]["@id"],
            )
            me_model_self = me_model["_self"]

        if simulation_resource["status"] != "SUCCESS":
            return to_simulation_response(
                encoded_simulation_id=encoded_simulation_id,
                simulation_resource=simulation_resource,
                me_model_self=me_model_self,
                synaptome_model_self=synaptome_model_self,
                distribution=None,
            )

        file_url = simulation_resource["distribution"]["contentUrl"]
        file_response = nexus_helper.fetch_file_by_url(file_url)
        results = file_response.json()

        return to_simulation_response(
            encoded_simulation_id=encoded_simulation_id,
            simulation_resource=simulation_resource,
            me_model_self=me_model_self,
            synaptome_model_self=synaptome_model_self,
            distribution=results,
        )

    except Exception as ex:
        logger.exception(f"Error fetching simulation results {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            message="retrieving simulation data failed",
            details=ex.__str__(),
        ) from ex