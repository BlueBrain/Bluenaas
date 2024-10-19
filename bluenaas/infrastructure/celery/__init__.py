from datetime import timedelta
import time
from celery import Celery
from celery.worker.control import inspect_command
from loguru import logger

from bluenaas.config.settings import settings
from bluenaas.utils.cpu_usage import get_cpus_in_use

celery_app = Celery(
    settings.CELERY_APP_NAME,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    task_default_queue=settings.CELERY_QUE_SIMULATIONS,
    task_acks_late=True,
    task_send_sent_event=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_compression="gzip",
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    result_expires=timedelta(minutes=0.5),
    result_backend_transport_options={"global_keyprefix": "bnaas_sim_"},
    include=["bluenaas.infrastructure.celery.bluenaas_task"],
)

celery_app.autodiscover_tasks(
    [
        "bluenaas.infrastructure.celery.tasks.create_simulation",
    ],
    force=True,
)


@inspect_command()
def cpu_usage_stats(state):
    """
    Retrieves the current CPU usage statistics.

    This function utilizes the `get_cpus_in_use` method to obtain information about
    the CPUs currently in use.

    Args:
        state: The current state or context, provided by the inspecting command.

    Returns:
        dict: A dictionary containing CPU usage statistics, which may include:
            - cpus_in_use
            - total_cpus
            - cpu_usage_percent
    """
    return get_cpus_in_use()


# NOTE: test task
@celery_app.task(bind=True, queue="simulations")
def create_dummy_task(self):
    logger.info("[TASK_RECEIVED_NOW]")
    if self.request.hostname.startswith("worker0"):
        time.sleep(20)
    else:
        time.sleep(20)
    return "me"
