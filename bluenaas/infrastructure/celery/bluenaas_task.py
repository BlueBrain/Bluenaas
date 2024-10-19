import json
from celery import Task
from loguru import logger

from bluenaas.infrastructure.celery.worker_scalability import EcsTaskProtection
from bluenaas.utils.run_on_env import run_on_env
from bluenaas.external.nexus.nexus import Nexus


class BluenaasTask(Task):
    track_started = True

    def __init__(self):
        self.task_protection = EcsTaskProtection()
        super().__init__()

    def before_start(self, task_id, args, kwargs):
        logger.info(f"[TASK_STARTED] {(task_id)}")

        if kwargs.get("enable_realtime") is False or kwargs.get("autosave") is True:
            logger.debug(f"Updating status for {task_id} to STARTED")
            assert "simulation_resource" in kwargs
            nexus_helper = Nexus(
                {
                    "token": kwargs["token"],
                    "model_self_url": kwargs["model_self"],
                }
            )
            nexus_helper.update_simulation_status(
                org_id=kwargs["org_id"],
                project_id=kwargs["project_id"],
                resource_self=kwargs["simulation_resource"]["_self"],
                status="started",
                is_draft=True,
            )
        super().before_start(task_id, args, kwargs)

        run_on_env(
            env_fns={
                "production": self.task_protection.toggle_protection,
            },
            is_protected=True,
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"[TASK_SUCCESS] {(task_id)}")

        if kwargs.get("enable_realtime") is False or kwargs.get("autosave") is True:
            logger.debug(f"Updating status for {task_id} to SUCCESS")
            assert "simulation_resource" in kwargs
            nexus_helper = Nexus(
                {
                    "token": kwargs["token"],
                    "model_self_url": kwargs["model_self"],
                }
            )
            nexus_helper.save_simulation_results(
                resource_self=kwargs["simulation_resource"]["_self"],
                config=json.loads(kwargs["config"]),
                stimulus_plot_data=json.loads(kwargs["stimulus_plot_data"]),
                org_id=kwargs["org_id"],
                project_id=kwargs["project_id"],
                status="success",
                is_draft=not kwargs.get("autosave"),
                results=retval["result"],
            )
        super().on_success(retval, task_id, args, kwargs)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.info(f"[TASK_FAILED] {(exc, task_id, args, kwargs, einfo)}")

        if kwargs.get("enable_realtime") is False or kwargs.get("autosave") is True:
            logger.debug(f"Updating status for {task_id} to FAILURE")
            assert "simulation_resource" in kwargs
            nexus_helper = Nexus(
                {
                    "token": kwargs["token"],
                    "model_self_url": kwargs["model_self"],
                }
            )
            nexus_helper.update_simulation_status(
                org_id=kwargs["org_id"],
                project_id=kwargs["project_id"],
                resource_self=kwargs["simulation_resource"]["_self"],
                status="failure",
                is_draft=not kwargs.get("autosave"),
                err=exc.__str__(),
            )

        super().on_failure(exc, task_id, args, kwargs, einfo)
        run_on_env(
            env_fns={
                "production": self.task_protection.extend_protection,
            },
            ets=5,
        )
