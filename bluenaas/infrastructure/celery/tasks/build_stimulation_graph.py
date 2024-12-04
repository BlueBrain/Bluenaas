import json
from loguru import logger
import billiard  # type: ignore
from billiard.queues import Empty as QueueEmptyException  # type: ignore

from bluenaas.infrastructure.celery import celery_app
from bluenaas.core.exceptions import StimulationPlotGenerationError
from bluenaas.domains.simulation import StimulationPlotConfig

STIMULATION_GRAPH_TIMEOUT_SECONDS = 5 * 60


@celery_app.task(
    bind=True,
    serializer="json",
)
def build_stimulation_graph(
    self,
    model_self: str,
    token: str,
    config: str,  # JSON string representing object of type StimulationPlotConfig
):
    queue = billiard.Queue()
    process = billiard.Process(
        target=_build_stimulation_graph_subprocess,
        args=(queue, model_self, token, config),
    )
    process.start()
    try:
        result = queue.get(timeout=STIMULATION_GRAPH_TIMEOUT_SECONDS)
        if isinstance(result, Exception):
            raise result

        return result
    except QueueEmptyException:
        raise StimulationPlotGenerationError(
            f"Did not receive stimulation plot in {STIMULATION_GRAPH_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        raise e
    finally:
        logger.debug("Cleaning up the worker process")
        process.join()
        logger.debug("Cleaning done")


def _build_stimulation_graph_subprocess(
    queue: billiard.Queue, model_self: str, token: str, config: str
) -> None:
    try:
        from bluenaas.core.model import model_factory
        from bluenaas.core.simulation_factory_plot import StimulusFactoryPlot

        stimulus_plot_config = StimulationPlotConfig(**json.loads(config))

        logger.debug(f"Started stimulation graph building for model {model_self}")

        model = model_factory(
            model_self=model_self,
            hyamp=None,
            bearer_token=token,
        )
        stimulus_factory_plot = StimulusFactoryPlot(
            stimulus_plot_config,
            model.threshold_current,
        )
        result_data = stimulus_factory_plot.apply_stim()

        queue.put(json.dumps(result_data))
    except Exception as e:
        logger.exception(
            f"Exception in celery worker during stimulation graph building {e}"
        )
        queue.put(
            StimulationPlotGenerationError(
                message=f"Exception in celery worker during stimulation graph building {e}"
            )
        )
    finally:
        logger.debug(f"Completed stimulation graph building for model {model_self}")
        return
