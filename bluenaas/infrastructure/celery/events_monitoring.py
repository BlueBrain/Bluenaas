import threading
from loguru import logger

from bluenaas.infrastructure.celery.worker_scalability import TaskScalabilityManager
from bluenaas.infrastructure.celery import celery_app


def main():
    def run_task():
        task = TaskScalabilityManager(
            celery_app=celery_app,
        )
        task.run()
        logger.info("[monitoring started]")

    monitor_thread = threading.Thread(target=run_task)
    monitor_thread.start()


if __name__ == "__main__":
    main()
