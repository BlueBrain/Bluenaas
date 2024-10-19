import redis
from loguru import logger
from bluenaas.config.settings import settings


queues_to_check = [
    settings.CELERY_QUE_SIMULATIONS,
]


def get_queue_depth(queue: str):
    try:
        r = redis.Redis.from_url(url=settings.CELERY_BROKER_URL)
        all_keys = r.keys()
        all_keys_decoded = [key.decode("utf-8") for key in all_keys]
        if queue in all_keys_decoded:
            queue_depth = r.llen(queue)
        return queue_depth
    except redis.RedisError as ex:
        logger.exception(f"error: Could not connect to Redis {ex}")
        return ex
    except Exception as ex:
        logger.warning(f"error: Redis error {ex}")
        return ex


def get_bulk_queues_depths(
    queues_to_check: list[str] | None = queues_to_check,
) -> dict[str, int]:
    """
    Get a list of queues and their message counts from Redis.
    """
    try:
        r = redis.Redis.from_url(url=settings.CELERY_BROKER_URL)
        all_keys = r.keys()
        all_keys_decoded = [key.decode("utf-8") for key in all_keys]

        if queues_to_check is None:
            raise ValueError("No queue was specified to be query")
        if queues_to_check:
            queues = [queue for queue in all_keys_decoded if queue in queues_to_check]

        depths = {}
        total = 0
        for queue in queues:
            try:
                queue_depth = get_queue_depth(queue)
                depths[queue] = queue_depth
                total += queue_depth if queue_depth is not None else 0
            except redis.RedisError as e:
                logger.exception(
                    f"error: could not retrieve depth for queue {queue}: {e}"
                )
                continue

        depths["total"] = total
        return depths

    except redis.RedisError as ex:
        logger.exception(f"error: could not connect to Redis {ex}")
        raise ex
    except Exception as ex:
        logger.exception(f"error: failed to gather queues data {ex}")
        raise ex
