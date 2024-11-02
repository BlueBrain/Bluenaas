from loguru import logger
from http import HTTPStatus
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.neuron_model import (
    SynaptomeModelResponse,
)
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)
from bluenaas.services.neuron_model.nexus_model_conversions import (
    nexus_synaptome_model_to_bluenaas_synaptome_model,
)


def get_synaptome_model_for_project(
    token: str, org_id: str, project_id: str, model_self: str
) -> SynaptomeModelResponse:
    nexus_helper = Nexus(
        {"token": token, "model_self_url": ""}
    )  # TODO: Remove model_id as a required field for nexus helper

    try:
        nexus_model = nexus_helper.fetch_resource_by_self(resource_self=model_self)
        file_url = nexus_model["distribution"]["contentUrl"]

        file_response = nexus_helper.fetch_file_by_url(file_url)
        distribution = file_response.json()

    except Exception as e:
        logger.error(f"Error when retrieving synaptome {model_self} from nexus {e}")
        raise BlueNaasError(
            message="Resource not found.",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            details="Please ensure that the model self is url-encoded.",
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    try:
        return nexus_synaptome_model_to_bluenaas_synaptome_model(
            nexus_model=nexus_model, distribution=distribution
        )
    except Exception as e:
        logger.exception(f"Cannot process incompatible nexus synaptome model {e}")
        raise BlueNaasError(
            message="Resource cannot be processed.",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
