from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue as QueueType
from typing import Any, Callable, Generator
from loguru import logger


def free_resources_after_streaming(
    fn: Callable[..., Generator[Any, Any, None]], queue: QueueType, process: BaseProcess
):
    try:
        for element in fn():
            yield element
    finally:
        logger.debug("Killing process and sub processes")
        queue.close()
        queue.join_thread()
        process.join()
        logger.debug("Cleaned up resources")
