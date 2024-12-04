import json
import re
from typing import Generator

from loguru import logger
from http import HTTPStatus as status

from bluenaas.utils.streaming import StreamingResponseWithCleanup, cleanup_worker
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    MorphologyGenerationError,
)
from bluenaas.infrastructure.celery.tasks.build_morphology_dendogram import (
    build_morphology_dendrogram,
)


def get_single_morphology_dendrogram(
    model_self: str,
    token: str,
    req_id: str,
):
    try:
        build_morphology_job = build_morphology_dendrogram.apply_async(
            kwargs={
                "model_self": model_self,
                "token": token,
            }
        )
        logger.debug(f"Started morphology dendogram task {build_morphology_job.id}")
        built_morphology_str = build_morphology_job.get()

        def stream_morphology_chunks() -> Generator[str, None, None]:
            if isinstance(built_morphology_str, MorphologyGenerationError):
                yield f"{json.dumps(
                    {
                        "error_code": BlueNaasErrorCode.MORPHOLOGY_GENERATION_ERROR,
                        "message": "Morphology generation failed",
                        "details": built_morphology_str.__str__(),
                    }
                )}\n"
                return

            chunks: list[str] = re.findall(r".{1,100000}", built_morphology_str)

            for index, chunk in enumerate(chunks):
                logger.debug(f"Queueing chunk {index} for morphology dendogram...")
                yield chunk

        return StreamingResponseWithCleanup(
            stream_morphology_chunks(),
            media_type="application/x-ndjson",
            finalizer=lambda: cleanup_worker(
                build_morphology_job.id,
            ),
        )

    except Exception as ex:
        logger.exception(f"retrieving morphology data failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="retrieving morphology data failed",
            details=ex.__str__(),
        ) from ex
