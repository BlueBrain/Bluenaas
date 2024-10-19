"""
Simulation Routes
contains the single neuron simulation endpoint (single neuron, single neuron with synaptome)
"""

from datetime import datetime
import time
from fastapi import APIRouter, Depends, Path, Query, Response, status
from typing import Optional


from bluenaas.config.settings import settings
from bluenaas.domains.nexus import DeprecateNexusResponse
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    SimulationResultItemResponse,
    SimulationType,
    PaginatedSimulationsResponse,
    StreamSimulationBodyRequest,
    StreamSimulationResponse,
)
from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.infrastructure.celery import create_dummy_task
from bluenaas.services.simulation.run_simulation import run_simulation
from bluenaas.services.simulation.stop_simulation import (
    StopSimulationResponse,
    stop_simulation,
)
from bluenaas.services.simulation.submit_simulation import submit_simulation
from bluenaas.core.exceptions import BlueNaasError
from bluenaas.services.simulation.fetch_simulation_status_and_results import (
    fetch_simulation_status_and_results,
)
from bluenaas.services.simulation.deprecate_simulation import deprecate_simulation
from bluenaas.services.simulation.fetch_all_simulations_for_project import (
    fetch_all_simulations_of_project,
)

router = APIRouter(
    prefix="/simulation",
    tags=["Simulation"],
)


@router.post(
    "/single-neuron/dummy",
    include_in_schema=settings.DEPLOYMENT_ENV != "production",
)
def dummy_simulation(
    tasks: int = Query(min=10, default=20),
):
    for i in range(tasks):
        create_dummy_task.apply_async()
        time.sleep(1)
        i += 1


@router.post(
    "/single-neuron/{org_id}/{project_id}/run-realtime",
    summary="Run neuron simulation realtime",
)
def execute_simulation(
    model_self: str,
    org_id: str,
    project_id: str,
    request: StreamSimulationBodyRequest,
    token: str = Depends(verify_jwt),
) -> StreamSimulationResponse:
    """
    Initiates a simulation for a single neuron or synaptome model and returns a simulation results in realtime.

    This endpoint starts the simulation process and allows for real-time updates of
    the simulation's progress. The response includes immediate details about the simulation
    task, enabling clients to track the status as it runs.

    > **Note**:
        This endpoint is designed for real-time simulation execution. Ensure the provided
        model ID and organization/project IDs are valid to avoid errors during the simulation start.
        Clients can use /stop endpoint to stop the simulation.
    """
    return run_simulation(
        org_id=org_id,
        project_id=project_id,
        model_self=model_self,
        config=request.config,
        autosave=request.autosave,
        token=token,
    )


@router.post(
    "/single-neuron/{org_id}/{project_id}/{task_id}/stop",
    summary=(
        """
        Stop neuron simulation
        """
    ),
)
async def kill_simulation(
    org_id: str,
    project_id: str,
    task_id: str,
    token: str = Depends(verify_jwt),
) -> StopSimulationResponse:
    """
    Stops a running simulation identified by the given task ID

    This endpoint can only stop simulations that were started using the
    `/run-realtime` endpoint.

    > **Note**:
        only available when simulation started by the /run-realtime endpoint
    """
    return await stop_simulation(
        token=token,
        task_id=task_id,
    )


@router.post(
    "/single-neuron/{org_id}/{project_id}/launch",
    summary="Run neuron simulation",
)
async def launch_simulation(
    model_self: str,
    org_id: str,
    project_id: str,
    config: SingleNeuronSimulationConfig,
    response: Response,
    token: str = Depends(verify_jwt),
) -> SimulationResultItemResponse:
    """
    Launches a simulation as a background task for a specified model
    This endpoint allows to initiate a simulation which will be processed
    in the background.
    """
    try:
        result = submit_simulation(
            token=token,
            model_self=model_self,
            org_id=org_id,
            project_id=project_id,
            config=config,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return result
    except BlueNaasError as e:
        response.status_code = e.http_status_code
        raise e
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise e


@router.get(
    "/single-neuron/{org_id}/{project_id}",
    summary=(
        """
        Get all neuron simulations per project
        """
    ),
)
async def get_all_simulations_for_project(
    org_id: str,
    project_id: str,
    simulation_type: Optional[SimulationType] = None,
    page_offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    token: str = Depends(verify_jwt),
) -> PaginatedSimulationsResponse:
    """
    Retrieves all simulations associated with a specific project.

    This endpoint allows users to fetch all simulations for a given project,
    identified by the organization ID and project ID. The results are paginated,
    and users can filter the simulations based on their creation dates and simulation type.

    > **Note**:
    Simulation results (x, y points) are not included in the response to avoid
    excessive data transfer.
    """
    return fetch_all_simulations_of_project(
        token=token,
        org_id=org_id,
        project_id=project_id,
        sim_type=simulation_type,
        offset=page_offset,
        size=page_size,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )


@router.get(
    "/single-neuron/{org_id}/{project_id}/{simulation_uri}",
    summary=(
        """
        Get simulation data
        """
    ),
)
async def get_simulation(
    org_id: str,
    project_id: str,
    simulation_uri: str = Path(
        ..., description="URL-encoded simulation URI (resource ID in nexus context)"
    ),
    token: str = Depends(verify_jwt),
) -> SimulationResultItemResponse:
    """
    Retrieves the results, status and metadata of a previously completed simulation.

    This endpoint allows to fetch the results and current status of a simulation
    identified by its URI. If the simulation is still in progress, the results will be
    returned as null. The organization ID and project ID are required to locate the
    specific simulation context.
    """
    return fetch_simulation_status_and_results(
        token=token,
        org_id=org_id,
        project_id=project_id,
        simulation_uri=simulation_uri,
    )


@router.delete(
    "/single-neuron/{org_id}/{project_id}/{simulation_uri}",
    summary="Delete simulation",
)
async def delete_simulation(
    org_id: str,
    project_id: str,
    simulation_uri: str = Path(
        ..., description="URL-encoded simulation URI (resource ID in nexus context)"
    ),
    token: str = Depends(verify_jwt),
) -> DeprecateNexusResponse:
    """
    Deletes a simulation resource identified by its URI (resource ID in nexus context)

    This endpoint allows  to delete a specific simulation resource
    based on the provided organization ID, project ID, and simulation URI.
    Once deleted, the simulation resource will no longer be accessible.
    """
    return deprecate_simulation(
        token=token,
        org_id=org_id,
        project_id=project_id,
        simulation_uri=simulation_uri,
    )
