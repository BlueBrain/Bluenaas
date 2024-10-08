from fastapi.responses import JSONResponse
from http import HTTPStatus


async def stop_simulation(
    token: str,
    task_id: str,
):
    from celery.result import AsyncResult
    from bluenaas.infrastructure.celery import celery_app

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
