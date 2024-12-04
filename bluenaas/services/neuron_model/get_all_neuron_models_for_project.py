from loguru import logger
from http import HTTPStatus
from typing import Optional
from datetime import datetime

from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.neuron_model import (
    MEModelResponse,
    ModelType,
    SynaptomeModelResponse,
)
from bluenaas.domains.simulation import PaginatedResponse
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)
from bluenaas.services.neuron_model.nexus_model_conversions import (
    convert_nexus_model,
    get_nexus_type,
)


def get_all_neuron_models_for_project(
    token: str,
    org_id: str,
    project_id: str,
    offset: int,
    size: int,
    model_type: Optional[ModelType],
    created_at_start: Optional[datetime],
    created_at_end: Optional[datetime],
) -> PaginatedResponse[MEModelResponse | SynaptomeModelResponse]:
    try:
        nexus_helper = Nexus({"token": token, "model_self_url": ""})

        nexus_model_response = nexus_helper.fetch_resources_of_type(
            org_label=None,
            project_label=None,
            res_types=get_nexus_type(model_type=model_type),
            offset=offset,
            size=size,
            created_at_start=created_at_start,
            created_at_end=created_at_end,
        )

        nexus_models = nexus_model_response["_results"]
        neuron_models = []

        for nexus_model in nexus_models:
            try:
                neuron_models.append(
                    convert_nexus_model(
                        nexus_model=nexus_model, nexus_helper=nexus_helper
                    )
                )

            except ValueError as e:
                # Ignore models that cannot be converted
                logger.exception(
                    f"Not sending {nexus_model["_self"]} in paginated response due to error {e}"
                )
            except Exception as e:
                logger.exception(
                    f"Could not fetch neuron_model {nexus_model["_self"]} from nexus {e}"
                )
        return PaginatedResponse[MEModelResponse | SynaptomeModelResponse](
            offset=offset,
            page_size=len(neuron_models),
            total=nexus_model_response["_total"],
            results=neuron_models,
        )
    except Exception as e:
        logger.exception(f"Error retrieving neuron models from nexus {e}")
        raise BlueNaasError(
            message="Error retrieving neuron models from nexus.",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
