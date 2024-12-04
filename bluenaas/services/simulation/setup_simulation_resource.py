from loguru import logger
from http import HTTPStatus
from typing import NamedTuple

from bluenaas.domains.simulation import (
    StimulationPlotConfig,
    SimulationStimulusConfig,
    StimulationItemResponse,
    SingleNeuronSimulationConfig,
)
from bluenaas.external.nexus.nexus import Nexus
from bluenaas.core.simulation_factory_plot import StimulusFactoryPlot
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    SimulationError,
)
from bluenaas.core.model import model_factory


class NexusSimulationDetails(NamedTuple):
    me_model_self: str
    synaptome_model_self: str | None
    stimulus_plot_data: list[StimulationItemResponse]
    simulation_resource: dict


def get_stimulation_plot_data(
    token: str, me_model_self: str, stimulus: SimulationStimulusConfig
) -> list[StimulationItemResponse]:
    logger.debug(f"REMOVE Stimulation plot data")
    model = model_factory(
        model_self=me_model_self,
        hyamp=None,
        bearer_token=token,
    )
    stimulus_config = StimulationPlotConfig(
        stimulus_protocol=stimulus.stimulus_protocol,
        amplitudes=stimulus.amplitudes
        if isinstance(stimulus.amplitudes, list)
        else [stimulus.amplitudes],
    )
    stimulus_factory_plot = StimulusFactoryPlot(
        stimulus_config,
        model.threshold_current,
    )
    plot_data = stimulus_factory_plot.apply_stim()
    for trace in plot_data:
        StimulationItemResponse.model_validate(trace)
    return plot_data


def setup_simulation_resources(
    token: str,
    model_self: str,
    org_id: str,
    project_id: str,
    config: SingleNeuronSimulationConfig,
    stimulus_plot_data: list[StimulationItemResponse],
) -> NexusSimulationDetails:
    nexus_helper = Nexus({"token": token, "model_self_url": model_self})
    # Step 1: Generate stimulus data to be saved in nexus resource in step 1
    try:
        me_model_self = model_self
        synaptome_model_self = None
        if config.type == "synaptome-simulation":
            synaptome_model_self = model_self
            synaptome_model = nexus_helper.fetch_resource_by_self(synaptome_model_self)
            me_model_id = synaptome_model["used"]["@id"]
            me_model = nexus_helper.fetch_resource_by_id(me_model_id)
            me_model_self = me_model["_self"]

    except Exception as ex:
        logger.exception(f"Generation of stimulus data failed {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.SIMULATION_ERROR,
            message="Generation of stimulus data failed",
            details=ex.__str__(),
        )

    # Step 2: Create nexus resource for simulation and set status "started"
    try:
        sim_response = nexus_helper.create_simulation_resource(
            simulation_config=config,
            stimulus_plot_data=stimulus_plot_data,
            status="started",
            org_id=org_id,
            project_id=project_id,
        )
        simulation_resource = nexus_helper.fetch_resource_for_org_project(
            org_label=org_id,
            project_label=project_id,
            resource_id=sim_response["@id"],
        )
    except SimulationError as ex:
        logger.exception(f"Creating nexus resource for simulation failed {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            message="Creating nexus resource for simulation failed",
            details=ex.__str__(),
        ) from ex
    except Exception as ex:
        logger.exception(f"Creating nexus resource for simulation failed {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.SIMULATION_ERROR,
            message="Creating nexus resource for simulation failed",
            details=ex.__str__(),
        ) from ex
    return NexusSimulationDetails(
        me_model_self=me_model_self,
        synaptome_model_self=synaptome_model_self,
        stimulus_plot_data=stimulus_plot_data,
        simulation_resource=simulation_resource,
    )
