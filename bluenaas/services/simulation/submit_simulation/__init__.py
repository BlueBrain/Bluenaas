import json
from loguru import logger
from urllib.parse import quote_plus

from bluenaas.domains.nexus import FullNexusSimulationResource
from bluenaas.domains.simulation import SingleNeuronSimulationConfig
from bluenaas.services.simulation.submit_simulation.setup_resources import (
    setup_simulation_resources,
)
from bluenaas.utils.simulation import convert_to_simulation_response


def submit_simulation(
    token: str,
    model_self: str,
    org_id: str,
    project_id: str,
    config: SingleNeuronSimulationConfig,
):
    """
    Starts a simulation  and returns simulation result and status when it finished,

    Args:
        token (str): Authorization token to access the simulation.
        model_self (str): The _self of the neuron model to simulate.
        org_id (str): The ID of the organization running the simulation.
        project_id (str): The ID of the project the simulation belongs to.
        config (SingleNeuronSimulationConfig): The simulation configuration.

    Returns:
        SimulationResultItemResponse
    """
    from bluenaas.infrastructure.celery.tasks.create_simulation import create_simulation

    (
        me_model_self,
        synaptome_model_self,
        stimulus_plot_data,
        sim_response,
        simulation_resource,
    ) = setup_simulation_resources(
        token,
        model_self,
        org_id,
        project_id,
        config,
    )

    # Step 2: Submit task to celery
    task = create_simulation.apply_async(
        kwargs={
            "org_id": org_id,
            "project_id": project_id,
            "model_self": model_self,
            "config": config.model_dump_json(),
            "token": token,
            "stimulus_plot_data": json.dumps(stimulus_plot_data),
            "simulation_resource": sim_response,
            "enable_realtime": False,
            "autosave": True,
        },
        ignore_result=True,
    )
    logger.debug(f"Task submitted with id {task.id}")

    # Step 3: Return simulation status to user
    return convert_to_simulation_response(
        simulation_uri=quote_plus(simulation_resource["@id"]),
        simulation_resource=FullNexusSimulationResource.model_validate(
            simulation_resource,
        ),
        me_model_self=me_model_self,
        synaptome_model_self=synaptome_model_self,
        distribution=None,
    )
