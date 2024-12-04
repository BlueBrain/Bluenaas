import json
from loguru import logger
import billiard  # type: ignore
from billiard.queues import Empty as QueueEmptyException  # type: ignore

from bluenaas.infrastructure.celery import celery_app
from bluenaas.core.exceptions import SynapseGenerationError
from bluenaas.domains.morphology import SynapsePlacementBody

SYNAPSE_PLACEMENT_TIMEOUT_SECONDS = 5 * 60


@celery_app.task(
    bind=True,
    serializer="json",
)
def place_synapses(
    self,
    model_self: str,
    token: str,
    synapse_placement_config: str,  # JSON string representing object of type StimulationPlotConfig
):
    queue = billiard.Queue()
    process = billiard.Process(
        target=_place_synapses_subprocess,
        args=(queue, model_self, token, synapse_placement_config),
    )
    process.start()
    try:
        result = queue.get(timeout=SYNAPSE_PLACEMENT_TIMEOUT_SECONDS)
        if isinstance(result, Exception):
            raise result

        return result
    except QueueEmptyException:
        raise SynapseGenerationError(
            f"Did not receive synaptome result in {SYNAPSE_PLACEMENT_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        raise e
    finally:
        logger.debug("Cleaning up the worker process")
        process.join()
        logger.debug("Cleaning done")


def _place_synapses_subprocess(
    queue: billiard.Queue, model_self: str, token: str, synapse_placement_config: str
) -> None:
    try:
        from bluenaas.core.model import model_factory

        placement_config = SynapsePlacementBody(**json.loads(synapse_placement_config))

        logger.debug(f"Started placing synapses for model {model_self}")
        model = model_factory(
            model_self=model_self,
            hyamp=None,
            bearer_token=token,
        )
        synapses = model.add_synapses(params=placement_config)

        queue.put(synapses.model_dump_json())
    except Exception as e:
        logger.exception(f"Exception in celery worker during placing synapses {e}")
        queue.put(SynapseGenerationError(message=f"Synaptome placement failed {e}"))
    finally:
        logger.debug(f"Completed placing synapses for model {model_self}")
        return
