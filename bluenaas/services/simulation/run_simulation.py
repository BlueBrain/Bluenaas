import json
from celery import states
from celery.result import AsyncResult
from loguru import logger
from celery.exceptions import TaskRevokedError
from fastapi import HTTPException, status

from bluenaas.core.exceptions import (
    BlueNaasError,
    ChildSimulationError,
    SimulationError,
)
from bluenaas.domains.simulation import (
    SimulationEvent,
    SingleNeuronSimulationConfig,
    StreamSimulationResponse,
)
from bluenaas.services.simulation.submit_simulation.setup_resources import (
    setup_simulation_resources,
)
from bluenaas.utils.get_last_progress_time import get_last_progress_time
from bluenaas.utils.streaming import StreamingResponseWithCleanup, cleanup_worker


task_state_descriptions = {
    "INIT": "Simulation is captured by the system",
    "PROGRESS": "Simulation is currently in progress.",
    "PENDING": "Simulation is waiting for execution.",
    "STARTED": "Simulation has started executing.",
    "SUCCESS": "The simulation completed successfully.",
    "FAILURE": "The simulation has failed.",
    "REVOKED": "The simulation has been canceled.",
}


def get_event_from_task_state(state) -> SimulationEvent:
    """
    Get the event type based on the task state.
    """
    if state in (states.PENDING, states.SUCCESS):
        event = "info"
    elif state == "PROGRESS":
        event = "data"
    elif state == states.FAILURE:
        event = "error"
    else:
        event = "info"

    return event.lower()


def run_simulation(
    token: str,
    model_self: str,
    org_id: str,
    project_id: str,
    config: SingleNeuronSimulationConfig,
    autosave: bool = False,
) -> StreamSimulationResponse:
    """
    Initiates a simulation task and streams real-time updates to the client.

    This function starts a simulation task asynchronously using Celery and streams real-time
    updates about the simulation's progress back to the client. It supports automatic saving
    of simulation results if the `autosave` option is enabled.

    Args:
        token (str): Authorization token to access the simulation and related resources.
        model_self (str): The identifier (_self) of the neuron model being simulated.
        org_id (str): The ID of the organization initiating the simulation.
        project_id (str): The ID of the project under which the simulation is being executed.
        config (SingleNeuronSimulationConfig): The configuration settings for the simulation.
        autosave (bool, optional): If `True`, the simulation results will be automatically saved.
                                   Defaults to `False`.

    Returns:
        StreamSimulationResponse: A streaming response containing real-time updates on the
                                  simulation task, including the task ID and status changes.

    Raises:
        Exception: If an error occurs during the streaming of simulation data.
    """
    from bluenaas.infrastructure.celery.tasks.create_simulation import create_simulation

    sim_response = None
    stimulus_plot_data = None

    try:
        if autosave:
            (
                _,
                _,
                stimulus_plot_data,
                sim_response,
                _,
            ) = setup_simulation_resources(
                token,
                model_self,
                org_id,
                project_id,
                SingleNeuronSimulationConfig.model_validate(config),
            )
    except BlueNaasError as e:
        raise HTTPException(
            status_code=e.http_status_code,
            detail=e.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.__str__(),
        )

    task = create_simulation.apply_async(
        kwargs={
            "model_self": model_self,
            "org_id": org_id,
            "project_id": project_id,
            "config": config.model_dump_json(),
            "token": token,
            "simulation_resource": sim_response if sim_response is not None else None,
            "stimulus_plot_data": json.dumps(stimulus_plot_data)
            if stimulus_plot_data is not None
            else None,
            "autosave": autosave,
        },
        ignore_result=True,
    )

    def streamify():
        """
        A generator that streams simulation updates to the client.

        Yields:
            str: A JSON-encoded message containing simulation info and status updates.
        """
        try:
            yield f"{json.dumps(
                {
                    "event": "init",
                    "description": task_state_descriptions["INIT"],
                    "state": "captured",
                    "task_id": task.id,
                    "data": None,
                }
            )}\n"

            lst = []
            while not task.ready():
                if (
                    isinstance(task.info, TaskRevokedError)
                    or isinstance(task.info, SimulationError)
                    or isinstance(task.info, ChildSimulationError)
                ):
                    yield build_stream_obj(task)
                    break
                if get_last_progress_time(task, lst):
                    yield build_stream_obj(task)

            if task.successful() or task.failed():
                yield build_stream_obj(task)

        except Exception as ex:
            logger.info(f"Exception in task streaming: {ex}")
            raise Exception("Trouble while streaming simulation data")

    return StreamingResponseWithCleanup(
        streamify(),
        finalizer=lambda: cleanup_worker(
            task.id,
        ),
        media_type="application/octet-stream",
        headers={
            "x-bnaas-task": task.id,
        },
    )


def build_stream_obj(task: AsyncResult):
    res = f"{json.dumps(
            {
                "event": get_event_from_task_state(task.state),
                "description": task_state_descriptions[task.state],
                "state": task.state.lower(),
                "task_id": task.id,
                "data": task.result or None,
            }
        )}\n"
    return res
