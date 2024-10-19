from datetime import datetime as dt

from loguru import logger


class CeleryEventLogger:
    def _to_timestamp(self, timestamp):
        return dt.fromtimestamp(timestamp) if timestamp is not None else None

    def log_task_status(self, task, event):
        logger.info(
            f"""[{self._to_timestamp(task.timestamp)}] 
                uuid:{task.uuid}
                name: {task.name} 
                type: {event["type"]} 
                state: {task.state.lower()}
            """
        )

    def log_event_details(self, event):
        print("event details: {}".format(event))

    def log_task_details(self, task):
        logger.info(f"task details: {task.name}")
        logger.info(f"uuid: {task.uuid}")
        logger.info(f"sent: {self._to_timestamp(task.sent)}")
        logger.info(f"state: {task.state}")


class CeleryEventsManager:
    def __init__(
        self,
        celery_app,
        verbose=False,
    ):
        self._app = celery_app
        self._state = celery_app.events.State()
        self._logger = CeleryEventLogger()
        self._verbose = verbose

    def _event_handler(handler):
        def wrapper(self, event):
            self._state.event(event)
            task = self._state.tasks.get(event["uuid"])
            self._logger.log_task_status(task, event)
            if self._verbose:
                self._logger.log_event_details(event)
                self._logger.log_task_details(task)
            handler(self, event)

        return wrapper

    @_event_handler
    def _on_task_sent(self, event):
        pass

    def _on_worker_online(self, event):
        pass

    def run(
        self,
        handlers: dict[str, any] | None = None,
    ):
        with self._app.connection() as connection:
            recv = self._app.events.Receiver(
                connection,
                handlers=handlers
                if handlers
                else {
                    "task-sent": self._on_task_sent,
                    "worker-online": self._on_worker_online,
                },
            )

            recv.capture(limit=None, timeout=10)
