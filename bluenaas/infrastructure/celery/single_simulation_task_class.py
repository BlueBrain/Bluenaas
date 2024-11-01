from celery import Task
from loguru import logger

from bluenaas.infrastructure.celery.worker_scalability import EcsTaskProtection
from bluenaas.infrastructure.celery.broker_manager import Lock
from bluenaas.utils.run_on_env import run_on_env


class SingleSimulationTask(Task):
    track_started = True

    def __init__(self):
        self.task_protection = EcsTaskProtection()
        self.locker = Lock("nexus_group")
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
        logger.info(f"[TASK_SUCCESS] {(task_id)} {kwargs} {retval}")
        # NOTE: sub simulation should be saved in the same simulation resource
        # NOTE: lock nexus call is required to not have race condition
        resource_self = kwargs["resource_self"]
        autosave = kwargs["autosave"]
        if resource_self is not None and autosave:
            # NOTE: saving into nexus concurrently may lead to race condition
            # NOTE: here I provide a lock by `resource_self` so other sub tasks can not update
            # the same resource until the previous one completed (the lock should be in success and failure state)
            # when releasing the lock from the previous one, the current one will take it over
            # TODO: make sure to release the lock at the `finally` block
            while self.locker.get_lock(resource_self) is not None:
                pass

            self.locker.acquire_lock(resource_self)
            try:
                pass
                # r = requests.get(
                #     resource_self,
                #     headers={
                #         "Authorization": kwargs["token"],
                #         "Content-Type": "application/json",
                #         "Accept": "*/*",
                #     },
                #     timeout=10,
                # )
                # TODO: get the latest version of the simulation
                # TODO: get the latest version of the simulation distribution file
                # TODO: continue the saving
                # TODO: saving to the same file should be possible in S3
                # TODO: please look into paper endpoint in core-web-app

            except Exception as ex:
                logger.exception(f"[SingleSimulationTask]/on_success: {ex}")
            finally:
                self.locker.release_lock(resource_self)

        super().on_success(retval, task_id, args, kwargs)
        # NOTE: release aws task definition protection (after 5min to allow reusability of the container)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.info(f"[TASK_FAILED] {(exc, task_id, args, kwargs, einfo)}")

        # NOTE: sub simulation should be saved in on same simulation resource
        # NOTE: lock nexus call is required
        resource_self = kwargs["resource_self"]
        autosave = kwargs["autosave"]
        if resource_self is not None and autosave:
            # NOTE: saving into nexus concurrently may lead to race condition
            # NOTE: here i provide a lock to by `resource_self` so other sub tasks can not update
            # the same resource until the previous one finished
            # when releasing the lock from the previous one, the current one will take it over
            # TODO: make sure to release the lock at the `finally` block
            pass

        super().on_failure(exc, task_id, args, kwargs, einfo)
        # NOTE: release aws task definition protection (after 5min to allow reusability of the container)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )
