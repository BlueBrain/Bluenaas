"""
Simulation Routes
contains the single neuron simulation endpoint (single neuron, single neuron with synaptome)
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from typing import Optional


from bluenaas.domains.nexus import DeprecateNexusResponse
from bluenaas.domains.simulation import (
    SimulationDetailsResponse,
    SimulationType,
    PaginatedResponse,
    SingleNeuronSimulationConfig,
)
from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.services.simulation.run_distributed_simulation import (
    run_distributed_simulation,
)

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
    "/single-neuron/{org_id}/{project_id}/run",
    summary="Run neuron simulation distributed per worker",
)
def distributed_simulation(
    model_id: str,
    org_id: str,
    project_id: str,
    config: SingleNeuronSimulationConfig,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_jwt),
    realtime: bool = True,
    autosave: bool = True,
):
    """
    Run a distributed neuron simulation across multiple instances, either in autosave or real-time mode.

    Parameters:
    -----------
    `org_id : str`
        The organization ID associated with the simulation.
    `project_id : str`
        The project ID associated with the simulation.
    `model_id : str`
        The URI or identifier for the neuron model being simulated.
    `realtime`: bool
        If realtime is true, simulation results are streamed in chunks. Response type is StreamingResponseWithCleanup.
        If realtime is false, simulation is started in the background and a HTTP JSON Response (of type BackgroundSimulationStatusResponse) or error is returned.
    `autosave`: bool
        If autosave is true, the results of simulations are automatically saved in the database. The response contains the resourceId that can be used to fetch these results.
        Please note, realtime=False and autosave=False is an invalid configuration.

    Returns:
    --------
    StreamingResponseWithCleanup or BackgroundSimulationStatusResponse
        If `realtime` is True, the response is a `StreamingResponseWithCleanup` that streams simulation state to the client.
        If `autosave` is True, the response is a BackgroundSimulationStatusResponse with simulation job details and resources.

    Raises:
    -------
    BlueNaasError
        Raised if there is an internal error during the simulation process.
    Exception
        Raised if there is an issue while streaming simulation data.

    Notes:
    ------
    - The function handles current-varying and frequency-varying simulations.
    - Tasks are distributed as individual simulation instances.
    - The simulation results are either streamed in real time or saved based on the `realtime` and `autosave` flags.
    - If `realtime` is enabled, streaming response is generated to update clients continuously about the state of the simulation.
        and if autosave is enabled too then result will be saved at the end of the simulation at the celery task definition
    - If `autosave` is enabled, the simulation state and results are stored and accessible later through Nexus queries.

    Workflow:
    ---------
    1. Prepare simulation resources if `autosave` is enabled.
    2. Pre-process the simulation, calculating synapses and building the model.
    3. Depending on the simulation type (current or frequency varying), generate tasks for simulation instances.
    4. Group and run tasks asynchronously using Celery's `group`.
    5. If `realtime`, stream the simulation results to the client.
    6. If `autosave`, return a job ID and resources for querying simulation status and results later.

    """
    return run_distributed_simulation(
        org_id=org_id,
        token=token,
        project_id=project_id,
        model_self=model_id,
        config=config,
        autosave=autosave,
        realtime=realtime,
        background_tasks=background_tasks,
    )


# @router.post(
#     "/single-neuron/{org_id}/{project_id}/{task_id}/shutdown",
#     summary=(
#         """
#         Stop neuron distributed simulation
#         """
#     ),
# )
# async def shutdown_simulation(
#     org_id: str,
#     project_id: str,
#     job_id: str,
#     token: str = Depends(verify_jwt),
# ) -> SimulationDetailsResponse:
#     """
#     Shutdown a running simulation identified by the given job ID (grouped simulations)
#     """
#     return await do_shutdown_simulation(
#         token=token,
#         task_id=job_id,
#     )


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
