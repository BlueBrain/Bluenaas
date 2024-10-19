from fastapi.responses import JSONResponse
from http import HTTPStatus

from pydantic import BaseModel

from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode


class StopSimulationResponse(BaseModel):
    task_id: str
    message: str


async def stop_simulation(
    token: str,
    task_id: str,
) -> StopSimulationResponse:
    from celery.result import AsyncResult
    from bluenaas.infrastructure.celery import celery_app

    try:
        task_result = AsyncResult(
            task_id,
            app=celery_app,
        )

        task_result.revoke(terminate=True)

        return JSONResponse(
            content={
                "task_id": task_id,
                "message": f"Simulation running by {task_id} is terminated",
            },
            status_code=HTTPStatus.ACCEPTED,
            headers={
                "x-bnaas-task": task_id,
            },
        )
    except Exception as ex:
        raise BlueNaasError(
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Error while stopping simulation",
            details=ex.__str__(),
        ) from ex
