import os
import threading
import time
from celery import Celery
from loguru import logger
import requests
from requests.adapters import Retry, HTTPAdapter
from bluenaas.config.settings import settings
from bluenaas.infrastructure.celery.aws import (
    get_cloudwatch_boto_client,
    get_ecs_boto_client,
)
from bluenaas.infrastructure.celery.events_manager import CeleryEventsManager
from bluenaas.infrastructure.celery.broker_manager import get_bulk_queues_depths
from bluenaas.utils.run_on_env import run_on_env

# NOTE: this global variable are just for testing/debugging
in_use_instances = 0


def set_in_use_instances_local(*, desired_instances: int):
    """
    Sets the global variable `in_use_instances` to the specified value.
    This is just for testing purposes

    Args:
        value (int): The new value to set for `in_use_instances`.

    Returns:
        tuple[int, int, int]: A tuple containing three integers:
            - The first two elements are fixed as 0.
            - The third element is the updated value of `in_use_instances`.

    Example:
        >>> set_in_use_instances_local(5)
        (0, 0, 5)
    """
    global in_use_instances
    in_use_instances = desired_instances
    logger.info(f"[SCALING] {in_use_instances=}")
    return (0, 0, 0, in_use_instances)


def get_in_use_instances_local():
    global in_use_instances
    return (0, 0, 0, in_use_instances)


class WorkerScalability:
    max_ecs_tasks = settings.AWS_MAX_ECS_TASKS

    def _get_ecs_task_status(self):
        """
        Retrieves the status of ECS tasks, including running and pending instances.

        Returns:
            tuple[int, int, int]:
                A tuple containing:
                - running_instances (int): The number of running ECS tasks.
                - pending_instances (int): The number of pending ECS tasks.
                - desired_instances (int): The number of desired ECS tasks.
                - in_use_instances (int): The total number of in-use ECS tasks (running + pending).
        """
        client = get_ecs_boto_client()
        service_type = client.describe_services(
            cluster=settings.AWS_CLUSTER_NAME,
            services=[
                settings.AWS_SERVICE_NAME,
            ],
        )["services"][0]
        running_instances = service_type["runningCount"]
        pending_instances = service_type["pendingCount"]
        desired_instances = service_type["desiredCount"]
        in_use_instances = running_instances + pending_instances

        return (
            running_instances,
            pending_instances,
            desired_instances,
            in_use_instances,
        )

    def _update_ecs_task(self, desired_instances: int):
        """
        Update the ECS service with the new desired task count.

        If the service's desired task count is different from the current one,
        the service will be updated with the new desired count.

        :param desired_count: The number of tasks to set for the ECS service.
        """

        client = get_ecs_boto_client()
        try:
            service_type = client.describe_services(
                cluster=settings.AWS_CLUSTER_NAME,
                services=[
                    settings.AWS_SERVICE_NAME,
                ],
            )
            if (
                service_type["services"]
                and service_type["services"][0]["desiredCount"] != desired_instances
            ):
                client.update_service(
                    cluster=settings.AWS_CLUSTER_NAME,
                    service=settings.AWS_SERVICE_NAME,
                    desiredCount=desired_instances,
                )
        except Exception as ex:
            logger.exception(f"update ecs cluster failed {ex}")

    def publish_queue_state_to_cloudwatch(
        self, queues_to_check: list[str], namespace: str
    ):
        """
        Publishes the state (depth) of specified queues to AWS CloudWatch.

        Args:
            queues_to_check (list[str]):
                A list of queue names whose depths will be checked and published.
            namespace (str):
                The CloudWatch namespace under which the metrics will be published.

        Returns:
            None
        """
        cloudwatch = get_cloudwatch_boto_client()
        depths = get_bulk_queues_depths(queues_to_check)

        for q in depths:
            try:
                cloudwatch.put_metric_data(
                    Namespace=namespace,
                    MetricData=[
                        {
                            "MetricName": q,
                            "Value": int(depths[q]),
                            "Timestamp": time.time(),
                            "Unit": "Count",
                        }
                    ],
                )

            except Exception as e:
                logger.exception(f"Publishing queues state to cloudwatch failed {e}")

    def scale_workers(self):
        to_provision_instances = get_bulk_queues_depths()["total"]
        needed_instances = min(to_provision_instances, self.max_ecs_tasks)

        return run_on_env(
            env_fns={
                "production": self._update_ecs_task,
                "development": set_in_use_instances_local,
            },
            fallback=None,
            desired_instances=needed_instances,
        )


class TaskScalabilityManager:
    def __init__(
        self,
        celery_app,
    ) -> None:
        self._celery_app: Celery = celery_app
        self.state = self._celery_app.events.State()
        self.scale_mng = WorkerScalability()

    def scale_up(self, event):
        logger.info(f"[NOTIFY][SCALE_UP] t:{get_bulk_queues_depths()["total"]}")
        self.scale_mng.scale_workers()

    def scale_down(self, event):
        logger.info(f"[NOTIFY][SCALE_DOWN] t:{get_bulk_queues_depths()["total"]}")
        self.scale_mng.scale_workers()

    def run(self):
        events_handler = CeleryEventsManager(
            celery_app=self._celery_app,
            verbose=False,
        )
        events_handler.run(
            handlers={
                # NOTE: the right event is "before_task_publish" or "after_task_publish" but this two events are not working
                # there is an open issue https://github.com/celery/celery/issues/3864
                "task-sent": self.scale_up,
                "task-succeeded": self.scale_down,
                "task-failed": self.scale_down,
                "task-revoked": self.scale_down,
            }
        )


class EcsTaskProtection:
    """
    This class handles enabling and disabling AWS ECS task scale-in protection.
    It interacts with the ECS Agent API to prevent tasks from being terminated
    during a scale-in event by toggling protection based on task state and queue depth.
    """

    def __init__(self) -> None:
        self.ser = requests.Session()

        retries = Retry(
            total=3,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504],
        )

        self.ser.mount("http://", HTTPAdapter(max_retries=retries))

    def toggle_protection(self, is_protected: bool = True, ets: int = None):
        """
        Toggles scale-in protection for the ECS task

        Args:
            is_protected (bool): Flag to enable/disable task protection.
                                 Defaults to `True`.
            ets (int): Expiration time for protection in minutes. If not provided,
                       defaults to `settings.AWS_TASK_PROTECTION_EXPIRE_IN_MIN`.

        Sends a request to the ECS Agent API using the `ECS_AGENT_URI` environment variable
        to toggle the task's protection state. Protection will expire after the specified
        time (or default if not specified).
        """
        self.ser.put(
            "http://{}/task-protection/v1/state".format(os.getenv("ECS_AGENT_URI", "")),
            headers={
                "Content-Type": "application/json",
            },
            json={
                "ProtectionEnabled": is_protected,
                "ExpiresInMinutes": ets
                if ets is not None
                else settings.AWS_TASK_PROTECTION_EXPIRE_IN_MIN,
            },
        )

    def extend_protection(self, ets: int = None):
        """
        Extends or disables task protection based on the queue depth.

        If there are pending tasks in the queue, protection is extended by the
        provided expiration time (`ets`) or defaults to 10 minutes. If no tasks
        are pending, protection is disabled.

        Args:
            ets (int): Expiration time for protection in minutes. If not provided,
                       defaults to 10 minutes.

        Uses `get_bulk_queues_depths()` to check the total number of pending tasks.
        If tasks are pending, protection is extended; otherwise, it is disabled.
        """

        if get_bulk_queues_depths()["total"] > 0:
            self.toggle_protection(True, ets if ets is not None else 10)
        else:
            self.toggle_protection(False)


def scale_controller():
    """
    Launches a background thread to monitor and control task scalability for Celery workers.

    This function starts a new thread that runs the `TaskScalabilityManager`.
    The `TaskScalabilityManager` is responsible for dynamically scaling Celery workers
    based on the queue size and task status. By running it in a
    separate thread, the main process remains unblocked, allowing other operations
    to continue in parallel.
    """

    from bluenaas.infrastructure.celery import celery_app

    def run_task():
        task = TaskScalabilityManager(
            celery_app=celery_app,
        )
        task.run()

    monitor_thread = threading.Thread(
        target=run_task,
    )
    monitor_thread.start()
