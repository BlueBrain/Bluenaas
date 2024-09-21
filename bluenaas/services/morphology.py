import json
import re
import signal
import multiprocessing as mp
from bluenaas.utils.streaming import free_resources_after_streaming
from fastapi.responses import StreamingResponse
from loguru import logger
from http import HTTPStatus as status
from threading import Event
from queue import Empty as QueueEmptyException
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    MorphologyGenerationError,
)
from bluenaas.core.model import model_factory
from bluenaas.utils.const import QUEUE_STOP_EVENT


def _build_morphology(
    model_id: str,
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
            model_id=model_id,
            hyamp=None,
            bearer_token=token,
        )
        morphology = model.CELL.get_cell_morph()
        morph_str = json.dumps(morphology)
        chunks: list[str] = re.findall(r".{1,100000}", morph_str)

        for index, chunk in enumerate(chunks):
            logger.debug(f"Queueing chunk {index} for morphology...")
            queue.put(chunk)

        queue.put(QUEUE_STOP_EVENT)

    except Exception as ex:
        logger.exception(f"Morphology builder error: {ex}")
        raise MorphologyGenerationError from ex
    finally:
        logger.debug("Morphology builder ended")


def get_single_morphology(
    model_id: str,
    token: str,
    req_id: str,
):
    try:
        ctx = mp.get_context("spawn")

        morpho_queue = ctx.Queue()
        stop_event = ctx.Event()

        process = ctx.Process(
            target=_build_morphology,
            args=(
                model_id,
                token,
                morpho_queue,
                stop_event,
            ),
            name=f"morphology_processor:{req_id}",
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
                        # Checking if queue is empty again to avoid the following race condition:
                        # t0 - Empty exception is raised from queue.get()
                        # t1 - Child process writes to queue
                        # t2 - Child process finishes
                        # t3 - Queue should be checked again for emptiness to capture the last message
                        continue
                    else:
                        raise Exception("Child process died unexpectedly")
                if q_result == QUEUE_STOP_EVENT or stop_event.is_set():
                    break

                yield q_result

        return StreamingResponse(
            free_resources_after_streaming(
                lambda: queue_streamify(
                    que=morpho_queue,
                    stop_event=stop_event,
                ),
                morpho_queue,
                process,
            ),
            media_type="application/x-ndjson",
        )

    except Exception as ex:
        logger.exception(f"retrieving morphology data failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="retrieving morphology data failed",
            details=ex.__str__(),
        ) from ex
