from celery import Celery
from datetime import timedelta

from bluenaas.config.settings import settings

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
    include=[
        "bluenaas.infrastructure.celery.full_simulation_task_class",
        "bluenaas.infrastructure.celery.single_simulation_task_class",
    ],
)

celery_app.autodiscover_tasks(
    [
        "bluenaas.infrastructure.celery.tasks.single_simulation_runner",
        "bluenaas.infrastructure.celery.tasks.create_simulation",
        "bluenaas.infrastructure.celery.tasks.initiate_simulation",
    ],
    force=True,
)
