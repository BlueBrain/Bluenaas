from celery import Task
from loguru import logger

from bluenaas.infrastructure.celery.worker_scalability import EcsTaskProtection
from bluenaas.utils.run_on_env import run_on_env


class SingleSimulationTask(Task):
    track_started = True

    def __init__(self):
        self.task_protection = EcsTaskProtection()
        super().__init__()

    def before_start(self, task_id, args, kwargs):
        logger.info(f"[TASK_STARTED] {(task_id)}")
        super().before_start(task_id, args, kwargs)
        # NOTE: acquire aws task protection
        run_on_env(
            env_fns={
                "production": self.task_protection.toggle_protection,
            },
            is_protected=True,
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"[TASK_SUCCESS] {(task_id)}")
        super().on_success(retval, task_id, args, kwargs)
        # NOTE: release aws task definition protection (after 5min to allow reusability of the container)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.info(f"[TASK_FAILED] {(exc, task_id, einfo)}")
        super().on_failure(exc, task_id, args, kwargs, einfo)
        # NOTE: release aws task definition protection (after 5min to allow reusability of the container)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )
