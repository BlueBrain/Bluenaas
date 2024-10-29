import json

from typing import Any, Optional

from bluenaas.core.stimulation.utils import (
    is_current_varying_simulation,
)
from bluenaas.core.stimulation.runners import (
    init_current_varying_simulation,
    init_frequency_varying_simulation,
)
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
)
from bluenaas.infrastructure.celery.full_simulation_task_class import BluenaasTask
from bluenaas.infrastructure.celery import celery_app


@celery_app.task(
    bind=True,
    base=BluenaasTask,
    serializer="json",
)
def create_simulation(
    self,
    *,
    org_id: str,
    project_id: str,
    model_self: str,
    config: dict,
    token: str,
    simulation_resource: Optional[dict[str, Any]] = None,
    stimulus_plot_data: Optional[list[dict[str, Any]]] = None,
    enable_realtime: bool = True,
    autosave: bool = False,
):
    """
    Creates a simulation based on the provided configuration and parameters.

    This task initializes a simulation using the provided configuration, which can either
    be current-varying or frequency-varying, depending on the setup.

    Args:
        self: The current task instance (automatically provided by Celery).
        org_id (str): The ID of the organization initiating the simulation.
        project_id (str): The ID of the project under which the simulation is executed.
        model_self (str): The identifier for the neuron model being simulated.
        config (dict): The configuration settings for the simulation, provided in a
                       JSON-serializable format.
        token (str): The authorization token used to authenticate and access necessary
                     resources for the simulation.
        simulation_resource (Optional[dict[str, Any]]): An optional resource object
                     that may contain additional data required for the simulation. Defaults to None.
        stimulus_plot_data (Optional[list[dict[str, Any]]]): Optional data for stimulus
                     plotting during the simulation. Defaults to None.
        enable_realtime (bool): Whether to enable real-time updates during the simulation.
                     Defaults to True.
        autosave (bool): Whether the simulation should be automatically saved after completion.
                     Defaults to False.

    Returns:
        dict: A dictionary containing the details of the created simulation, including:
            - org_id (str): The organization ID.
            - project_id (str): The project ID.
            - model_self (str): The neuron model identifier used in the simulation.
            - config (dict): The configuration settings used for the simulation.
            - result: The result of the simulation.
    """
    cf = SingleNeuronSimulationConfig(**json.loads(config))

    if is_current_varying_simulation(cf):
        result = init_current_varying_simulation(
            model_self,
            token,
            cf,
            enable_realtime=enable_realtime,
        )
    else:
        result = init_frequency_varying_simulation(
            model_self,
            token,
            cf,
            enable_realtime=enable_realtime,
        )

    return {
        "org_id": org_id,
        "project_id": project_id,
        "model_self": model_self,
        "config": config,
        "result": result,
        "simulation_resource": simulation_resource,
        "stimulus_plot_data": stimulus_plot_data,
    }
