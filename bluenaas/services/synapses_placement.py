from loguru import logger
from http import HTTPStatus as status
import json

from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)
from bluenaas.domains.morphology import SynapsePlacementBody, SynapsePlacementResponse
from bluenaas.infrastructure.celery.tasks.place_synapses import place_synapses


def generate_synapses_placement(
    model_self: str,
    token: str,
    req_id: str,
    params: SynapsePlacementBody,
) -> SynapsePlacementResponse:
    try:
        stimulation_graph_job = place_synapses.apply_async(
            kwargs={
                "model_self": model_self,
                "token": token,
                "synapse_placement_config": params.model_dump_json(),
            }
        )
        logger.debug(f"Started synapses placement job {stimulation_graph_job.id}")
        synapse_placement_result = stimulation_graph_job.get()

        return SynapsePlacementResponse(**json.loads(synapse_placement_result))
    except Exception as ex:
        logger.exception(f"Exception in synapse placement {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Placing synapses failed",
            details=ex.__str__(),
        ) from ex
