import json
from loguru import logger
from http import HTTPStatus as status
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
)
from bluenaas.domains.simulation import StimulationPlotConfig
from bluenaas.infrastructure.celery.tasks.build_stimulation_graph import (
    build_stimulation_graph,
)


def get_direct_current_plot_data(
    model_self: str,
    config: StimulationPlotConfig,
    token: str,
    req_id: str,
):
    try:
        stimulation_graph_job = build_stimulation_graph.apply_async(
            kwargs={
                "model_self": model_self,
                "token": token,
                "config": config.model_dump_json(),
            }
        )
        logger.debug(f"Started stimulation graph job {stimulation_graph_job.id}")
        graph_result = stimulation_graph_job.get()

        return json.loads(graph_result)
    except Exception as ex:
        logger.exception(f"Exception in direct current plot {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Building stimulation plot failed",
            details=ex.__str__(),
        ) from ex
