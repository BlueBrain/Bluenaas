import signal
import multiprocessing as mp
from loguru import logger
from http import HTTPStatus as status
from queue import Empty as QueueEmptyException

from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    SynapseGenerationError,
)
from bluenaas.core.model import model_factory
from bluenaas.domains.morphology import SynapsePlacementBody, SynapsePlacementResponse
from bluenaas.utils.const import QUEUE_STOP_EVENT


def _generate_synapses(
    model_self: str,
    token: str,
    params: SynapsePlacementBody,
    queue: mp.Queue,
    stop_event: mp.Event,
):
    def stop_process():
        stop_event.set()

    signal.signal(signal.SIGTERM, stop_process)
    signal.signal(signal.SIGINT, stop_process)

    try:
        model = model_factory(
            model_self=model_self,
            hyamp=None,
            bearer_token=token,
        )

        synapses = model.add_synapses(params)
        queue.put(synapses)
        queue.put(QUEUE_STOP_EVENT)
    except SynapseGenerationError as ex:
        queue.put(ex)
    except Exception as ex:
        logger.exception(f"Synapses generator error: {ex}")
        raise SynapseGenerationError from ex
    finally:
        logger.debug("Synapses generator ended")


def generate_synapses_placement(
    model_self: str,
    token: str,
    req_id: str,
    params: SynapsePlacementBody,
) -> SynapsePlacementResponse:
    try:
        ctx = mp.get_context("spawn")

        synapses_queue = ctx.Queue()
        stop_event = ctx.Event()
        process = ctx.Process(
            target=_generate_synapses,
            args=(model_self, token, params, synapses_queue, stop_event),
            name=f"synapses_processor:{req_id}",
        )
        process.daemon = True
        process.start()

        synapses = None
        try:
            while True:
                try:
                    record = synapses_queue.get(timeout=1)
                except QueueEmptyException:
                    if process.is_alive():
                        continue
                    if not synapses_queue.empty():
                        continue
                    else:
                        raise Exception("Child process died unexpectedly")
                if isinstance(record, SynapseGenerationError):
                    raise record
                if record == QUEUE_STOP_EVENT or stop_event.is_set():
                    break
                if record is not None:
                    synapses = record
                    break
        finally:
            synapses_queue.close()
            synapses_queue.join_thread()
            process.join()
        return synapses
    except SynapseGenerationError as ex:
        raise BlueNaasError(
            http_status_code=status.BAD_REQUEST,
            error_code=BlueNaasErrorCode.SYNAPSE_PLACEMENT_ERROR,
            message="generating synapses placement failed",
            details=ex.__str__(),
        ) from ex
    except Exception as ex:
        # logger.exception(f"generating synapses placement failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="generating synapses placement failed",
            details=ex.__str__(),
        ) from ex
