from loguru import logger
from http import HTTPStatus
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.neuron_model import SynaptomeModelResponse, MEModelResponse
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)
from bluenaas.services.neuron_model.nexus_model_conversions import convert_nexus_model


def get_neuron_model_for_project(
    token: str, org_id: str, project_id: str, model_self: str
) -> MEModelResponse | SynaptomeModelResponse:
    nexus_helper = Nexus(
        {"token": token, "model_self_url": ""}
    )  # TODO: Remove model_id as a required field for nexus helper

    try:
        nexus_model = nexus_helper.fetch_resource_by_self(resource_self=model_self)
        return convert_nexus_model(nexus_model=nexus_model, nexus_helper=nexus_helper)
    except ValueError as e:
        logger.exception(f"Error when converting nexus model from nexus {e}")
        raise BlueNaasError(
            message="Resource could not be converted to a model response",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        logger.error(f"Error when retrieving synaptome {model_self} from nexus {e}")
        raise BlueNaasError(
            message="Resource not found.",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            details="Please ensure that the model self is url-encoded.",
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )
