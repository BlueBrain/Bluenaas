"""
Simulation Routes
contains the single neuron simulation endpoint (single neuron, single neuron with synaptome)
"""

from fastapi import APIRouter, Depends, Request, Query, BackgroundTasks
from typing import Optional
from datetime import datetime

from bluenaas.domains.simulation import (
    SimulationDetailsResponse,
    SingleNeuronSimulationConfig,
    SimulationType,
    PaginatedResponse,
)
from bluenaas.domains.nexus import DeprecateNexusResponse
from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.services.single_neuron_simulation import execute_single_neuron_simulation
from bluenaas.services.submit_simulaton import submit_background_simulation
from bluenaas.services.submit_simulaton.fetch_simulation_status_and_results import (
    fetch_simulation_status_and_results,
)
from bluenaas.services.submit_simulaton.deprecate_simulation import deprecate_simulation
from bluenaas.services.submit_simulaton.fetch_all_simulations_of_project import (
    fetch_all_simulations_of_project,
)

router = APIRouter(prefix="/simulation")


@router.post("/single-neuron/{org_id}/{project_id}/run", tags=["simulation"])
def run_simulation(
    request: Request,
    org_id: str,
    project_id: str,
    model_id: str,
    config: SingleNeuronSimulationConfig,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_jwt),
    realtime: bool = True,
):
    """
    Run a neuron simulation and optionally get results in realtime.
    If `realtime` query parameter is False only the simulation id is returned which can be used to retrieve status and result
    of simulation.

    Returns:
    --------
    If realtime is True - A StreamingResponse is returned which contains chunks of simulation data of type `SimulationItemResponse`

    If realtime is False - `BackgroundSimulationStatusResponse` is returned with simulation `id`. This `id` can be url-encoded and
    used to later query the status (and get result if any) of simulation.
    """
    if realtime is True:
        return execute_single_neuron_simulation(
            org_id=org_id,
            project_id=project_id,
            model_id=model_id,
            token=token,
            config=config,
            req_id=request.state.request_id,
            realtime=realtime,
        )
    else:
        return submit_background_simulation(
            org_id=org_id,
            project_id=project_id,
            model_self=model_id,
            config=config,
            token=token,
            background_tasks=background_tasks,
            request_id=request.state.request_id,
        )


@router.get(
    "/single-neuron/{org_id}/{project_id}",
    description="Get all simulations for a project",
    summary=(
        """
        Returns all simulations in the provided project. 
        Please note, the data for simulations does not contain simulation results (x, y points) 
        or simulation config to not bloat the response.
        Only nexus simulations that conform with the latest schema are returned.
        """
    ),
    tags=["simulation"],
)
async def get_all_simulations_for_project(
    org_id: str,
    project_id: str,
    simulation_type: Optional[SimulationType] = None,
    offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    token: str = Depends(verify_jwt),
) -> PaginatedResponse[SimulationDetailsResponse]:
    return fetch_all_simulations_of_project(
        token=token,
        org_id=org_id,
        project_id=project_id,
        sim_type=simulation_type,
        offset=offset,
        size=page_size,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )


@router.get(
    "/single-neuron/{org_id}/{project_id}/{simulation_id:path}",
    summary=(
        """
        Get results & status for a previously started simulation. 
        If simulation is not complete the results are null.
        `simulation_id` should be url encoded.
        """
    ),
    tags=["simulation"],
)
async def get_simulation(
    org_id: str,
    project_id: str,
    simulation_id: str,
    token: str = Depends(verify_jwt),
) -> SimulationDetailsResponse:
    return fetch_simulation_status_and_results(
        token=token,
        org_id=org_id,
        project_id=project_id,
        simulation_uri=simulation_id,
    )


@router.delete(
    "/single-neuron/{org_id}/{project_id}/{simulation_id:path}",
    summary="Delete simulation resource",
    tags=["simulation"],
)
async def delete_simulation(
    org_id: str,
    project_id: str,
    simulation_id: str,
    token: str = Depends(verify_jwt),
) -> DeprecateNexusResponse:
    return deprecate_simulation(
        token=token,
        org_id=org_id,
        project_id=project_id,
        simulation_uri=simulation_id,
    )
