import json
import re
import signal
import multiprocessing as mp
from multiprocessing.synchronize import Event
from bluenaas.utils.streaming import StreamingResponseWithCleanup, cleanup
from loguru import logger
from http import HTTPStatus as status
from queue import Empty as QueueEmptyException
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    MorphologyGenerationError,
)
from bluenaas.core.model import model_factory
from bluenaas.utils.const import QUEUE_STOP_EVENT


def _build_morphology_dendrogram(
    model_self: str,
    token: str,
    queue: mp.Queue,
    stop_event: Event,
):
    def stop_process():
        stop_event.set()

    signal.signal(signal.SIGTERM, stop_process)
    signal.signal(signal.SIGINT, stop_process)

    try:
        model = model_factory(
            model_self=model_self,
            hyamp=None,
            bearer_token=token,
        )
        morphology_dendrogram = model.CELL.get_dendrogram()
        morph_dend_str = json.dumps(morphology_dendrogram)

        chunks: list[str] = re.findall(r".{1,100000}", morph_dend_str)

        for index, chunk in enumerate(chunks):
            logger.debug(f"Queueing chunk {index} for morphology dendrogram...")
            queue.put(chunk)

        queue.put(QUEUE_STOP_EVENT)

    except Exception as ex:
        queue.put(QUEUE_STOP_EVENT)
        logger.exception(f"Morphology dendrogram builder error: {ex}")
        raise MorphologyGenerationError from ex
    finally:
        logger.debug("Morphology dendrogram builder ended")


def get_single_morphology_dendrogram(
    model_self: str,
    token: str,
    req_id: str,
):
    try:
        ctx = mp.get_context("spawn")

        morpho_dend_queue = ctx.Queue()
        stop_event = ctx.Event()

        process = ctx.Process(
            target=_build_morphology_dendrogram,
            args=(
                model_self,
                token,
                morpho_dend_queue,
                stop_event,
            ),
            name=f"morphology_dendrogram_processor:{req_id}",
        )
        process.daemon = True
        process.start()

        def queue_streamify(
            que: mp.Queue,
            stop_event: Event,
        ):
            while True:
                try:
                    q_result = que.get(timeout=1)
                except QueueEmptyException:
                    if process.is_alive():
                        continue
                    if not que.empty():
                        continue
                    else:
                        raise Exception("Child process died unexpectedly")
                if q_result == QUEUE_STOP_EVENT or stop_event.is_set():
                    break

                yield q_result

        return StreamingResponseWithCleanup(
            queue_streamify(que=morpho_dend_queue, stop_event=stop_event),
            media_type="application/x-ndjson",
            finalizer=lambda: cleanup(stop_event, process),
        )

    except Exception as ex:
        logger.exception(f"retrieving morphology dendrogram data failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="retrieving morphology dendrogram data failed",
            details=ex.__str__(),
        ) from ex
