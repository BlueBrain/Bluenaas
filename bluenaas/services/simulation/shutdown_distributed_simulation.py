from fastapi.responses import JSONResponse
from http import HTTPStatus

from pydantic import BaseModel

from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode


class StopSimulationResponse(BaseModel):
    job_id: str
    message: str


async def do_shutdown_simulation(
    token: str,
    job_id: str,
) -> StopSimulationResponse:
    from celery.result import GroupResult
    from bluenaas.infrastructure.celery import celery_app

    try:
        job_result = GroupResult(
            job_id,
            app=celery_app,
        )

        job_result.revoke(terminate=True)

        return JSONResponse(
            content={
                "task_id": job_id,
                "message": f"Simulation running by {job_id} is terminated",
            },
            status_code=HTTPStatus.ACCEPTED,
            headers={
                "x-bnaas-job": job_id,
            },
        )
    except Exception as ex:
        raise BlueNaasError(
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Error while shuting down grouped simulation ",
            details=ex.__str__(),
        ) from ex
