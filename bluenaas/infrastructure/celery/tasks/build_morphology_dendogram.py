import json
from loguru import logger
import billiard  # type: ignore
from billiard.queues import Empty as QueueEmptyException  # type: ignore

from bluenaas.infrastructure.celery import celery_app
from bluenaas.core.exceptions import MorphologyGenerationError

MORPHOLOGY_BUILD_TIMEOUT_SECONDS: int = 5 * 60


@celery_app.task(
    bind=True,
    serializer="json",
)
def build_morphology_dendrogram(
    self,
    model_self: str,
    token: str,
):
    queue = billiard.Queue()
    process = billiard.Process(
        target=_build_morphology_dendogram_subprocess,
        args=(queue, model_self, token),
    )
    process.start()
    try:
        result = queue.get(timeout=MORPHOLOGY_BUILD_TIMEOUT_SECONDS)
        if isinstance(result, Exception):
            raise result

        return result
    except QueueEmptyException:
        raise MorphologyGenerationError(
            f"Did not receive morphology dendogram result in {MORPHOLOGY_BUILD_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        raise e
    finally:
        logger.debug("Cleaning up the worker process")
        process.join()
        logger.debug("Cleaning done")


def _build_morphology_dendogram_subprocess(
    queue: billiard.Queue, model_self: str, token: str
) -> None:
    try:
        from bluenaas.core.model import model_factory

        logger.debug(f"Started building morphology dendogram for model {model_self}")
        model = model_factory(
            model_self=model_self,
            hyamp=None,
            bearer_token=token,
        )
        morphology_dendrogram = model.CELL.get_dendrogram()
        queue.put(json.dumps(morphology_dendrogram))
    except Exception as e:
        logger.exception(
            f"Exception in celery worker during morphology dendogram building {e}"
        )
        queue.put(
            MorphologyGenerationError(
                message=f"Morphology dendogram generation failed {e}"
            )
        )
    finally:
        logger.debug(f"Finished building morphology dendogram for model {model_self}")
        return
