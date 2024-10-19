import json
from loguru import logger
from celery.signals import before_task_publish, after_task_publish, worker_ready

from bluenaas.domains.simulation import SingleNeuronSimulationConfig
from bluenaas.infrastructure.celery import celery_app


@worker_ready.connect
def worker_connect(sender, *args, **kwargs):
    logger.info(f"args --> {args=}")
    logger.info(f"sender --> {sender=}")
    logger.info(f"kwargs --> {kwargs=}")
    pass


@before_task_publish.connect
def before_task(
    body, exchange, routing_key, headers, properties, declare, retry_policy, **kwargs
):
    logger.info("@@before_task_publish")
    logger.info(f"@@config, {body[1]["config"]} {type(body[1]["config"])}")
    _config = SingleNeuronSimulationConfig.model_validate(json.loads(body[1]["config"]))
    cpu_needed = len(_config.current_injection.stimulus.amplitudes)
    logger.info(f"@@__cpu_needed__: {cpu_needed}")
    logger.info(f"@@__all_stats__: {celery_app.control.inspect().stats()}")
    logger.info(f"@@__all_stats__: {celery_app.control.inspect().active()}")
    logger.info("@@")
    pass


@after_task_publish.connect
def after_task(headers, body, exchange, routing_key, **kwargs):
    logger.info("@@after_task_publish")
    # logger.info(f"@@body, {body}")
    logger.info("@@")
    pass
