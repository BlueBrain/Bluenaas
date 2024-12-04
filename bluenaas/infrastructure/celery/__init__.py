from celery import Celery  # type: ignore
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
    result_expires=timedelta(seconds=0.5),
    result_backend_transport_options={"global_keyprefix": "bnaas_sim_"},
    include=[
        "bluenaas.infrastructure.celery.full_simulation_task_class",
        "bluenaas.infrastructure.celery.single_simulation_task_class",
    ],
)

celery_app.conf.task_routes = {
    "bluenaas.infrastructure.celery.tasks.build_morphology.build_morphology": {
        "queue": settings.CELERY_FAST_TASKS_QUEUE,
    },
    "bluenaas.infrastructure.celery.tasks.build_morphology_dendogram.build_morphology_dendrogram": {
        "queue": settings.CELERY_FAST_TASKS_QUEUE,
    },
    "bluenaas.infrastructure.celery.tasks.build_stimulation_graph.build_stimulation_graph": {
        "queue": settings.CELERY_FAST_TASKS_QUEUE,
    },
    "bluenaas.infrastructure.celery.tasks.place_synapses.place_synapses": {
        "queue": settings.CELERY_FAST_TASKS_QUEUE,
    },
}


celery_app.autodiscover_tasks(
    [
        "bluenaas.infrastructure.celery.tasks.single_simulation_runner",
        "bluenaas.infrastructure.celery.tasks.create_simulation",
        "bluenaas.infrastructure.celery.tasks.initiate_simulation",
        "bluenaas.infrastructure.celery.tasks.build_morphology",
        "bluenaas.infrastructure.celery.tasks.build_morphology_dendogram",
        "bluenaas.infrastructure.celery.tasks.build_stimulation_graph",
        "bluenaas.infrastructure.celery.tasks.place_synapses",
    ],
    force=True,
)
