from loguru import logger
from http import HTTPStatus
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.neuron_model import (
    SynaptomeModelResponse,
    UsedMEModel,
)
from bluenaas.domains.morphology import SynapseConfig
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)


def get_synaptome_model_for_project(
    token: str, org_id: str, project_id: str, model_self: str
) -> SynaptomeModelResponse:
    nexus_helper = Nexus(
        {"token": token, "model_self_url": ""}
    )  # TODO: Remove model_id as a required field for nexus helper

    try:
        nexus_model = nexus_helper.fetch_resource_by_self(resource_self=model_self)
    except Exception as e:
        logger.error(f"Error when retrieving synaptome {model_self} from nexus {e}")
        raise BlueNaasError(
            message="Resource not found.",
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            details="Please ensure that the model self is url-encoded.",
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    file_url = nexus_model["distribution"]["contentUrl"]

    file_response = nexus_helper.fetch_file_by_url(file_url)
    distribution = file_response.json()

    synapses = distribution["synapses"]
    me_model_self = distribution["meModelSelf"]

    synaptome_model = SynaptomeModelResponse(
        self=nexus_model["_self"],
        name=nexus_model["name"],
        description=nexus_model.get("description"),
        model_type="synaptome",
        created_by=nexus_model["_createdBy"],
        created_at=nexus_model["_createdAt"],
        me_model=UsedMEModel(
            model_self=me_model_self,
            model_type="me-model",
            name=nexus_model["used"]["name"],
        ),
        synapses=[SynapseConfig.model_validate(synapse) for synapse in synapses],
    )

    return synaptome_model
