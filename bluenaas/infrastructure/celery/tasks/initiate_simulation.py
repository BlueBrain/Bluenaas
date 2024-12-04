"""
This task is responsible for building the neuron model and configuring the synaptic series.

Overview:
---------
- Ensures that the neuron model and any required mechanisms are available.
- If the model or mechanisms are not present, it will compile or build them as needed.
- This task must be executed prior to running any simulation to guarantee that the model is fully prepared.

Purpose:
--------
By executing this task, the system validates the model's availability and configures the necessary synaptic series,
which are essential for both current- and frequency-varying simulations. This process is crucial for initializing
the simulation environment and ensuring that subsequent tasks run efficiently.

"""

from itertools import chain
import json
from loguru import logger
import billiard  # type: ignore
from billiard.queues import Empty as QueueEmptyException  # type: ignore

from bluenaas.core.exceptions import SimulationError
from bluenaas.core.model import Model, SynaptomeDetails, fetch_synaptome_model_details
from bluenaas.core.stimulation.utils import (
    get_constant_frequencies_for_sim_id,
    get_sim_configs_by_synapse_id,
    get_synapse_placement_config,
    is_current_varying_simulation,
)
from bluenaas.infrastructure.celery import celery_app
from bluenaas.domains.morphology import SynapseMetadata
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    SynaptomeSimulationConfig,
    SimulationStimulusConfig,
    StimulationPlotConfig,
)
from bluenaas.utils.serializer import (
    serialize_synapse_series_dict,
    serialize_synapse_series_list,
    serialize_template_params,
)
from bluenaas.utils.util import log_stats_for_series_in_frequency

SIMULATION_INITIALIZATION_TIMEOUT_SECONDS = 6 * 60


@celery_app.task(
    bind=True,
    serializer="json",
)
def initiate_simulation(
    self,
    model_self: str,
    token: str,
    config: str,  # Json str representing SingleNeuronSimulationConfig
    stimulation_config: str | None,  # Json str representing SimulationStimulusConfig
):
    queue = billiard.Queue()
    process = billiard.Process(
        target=_initiate_simulation_subprocess,
        args=(queue, model_self, token, config, stimulation_config),
    )
    process.start()
    try:
        result = queue.get(timeout=SIMULATION_INITIALIZATION_TIMEOUT_SECONDS)
        if isinstance(result, Exception):
            raise result

        return result
    except QueueEmptyException:
        raise SimulationError(
            f"Could not initialize simulation in {SIMULATION_INITIALIZATION_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        raise e
    finally:
        logger.debug("Cleaning up the worker process")
        process.join()
        logger.debug("Cleaning done")


def _initiate_simulation_subprocess(
    queue: billiard.Queue,
    model_self: str,
    token: str,
    config: str,
    stimulation_config: str,
) -> None:
    try:
        logger.info("[initiate simulation]")
        from bluenaas.core.model import model_factory
        from bluenaas.core.simulation_factory_plot import StimulusFactoryPlot

        cf = SingleNeuronSimulationConfig(**json.loads(config))
        stim_config = (
            SimulationStimulusConfig(**json.loads(stimulation_config))
            if stimulation_config is not None
            else None
        )

        me_model_id = model_self
        synaptome_details = None

        if cf.type == "synaptome-simulation" and cf.synaptome is not None:
            synaptome_details = fetch_synaptome_model_details(
                synaptome_self=model_self, bearer_token=token
            )
            me_model_id = synaptome_details.base_model_self

        model = model_factory(
            model_self=me_model_id,
            hyamp=cf.conditions.hypamp,
            bearer_token=token,
        )

        cell = model.CELL._cell
        template_params = cell.template_params

        if stim_config is not None:
            stimulus_config = StimulationPlotConfig(
                stimulus_protocol=stim_config.stimulus_protocol,
                amplitudes=stim_config.amplitudes
                if isinstance(stim_config.amplitudes, list)
                else [stim_config.amplitudes],
            )
            stimulus_factory_plot = StimulusFactoryPlot(
                stimulus_config,
                model.threshold_current,
            )
            stim_plot_data = stimulus_factory_plot.apply_stim()

        (synapse_generation_config, frequency_to_synapse_config) = (
            setup_synapses_series(
                cf,
                synaptome_details,
                model,
            )
        )

        output = (
            me_model_id,
            serialize_template_params(template_params),  # TODO: Remove
            serialize_synapse_series_list(synapse_generation_config)
            if synapse_generation_config is not None
            else None,
            serialize_synapse_series_dict(frequency_to_synapse_config)
            if frequency_to_synapse_config is not None
            else None,
            json.dumps(stim_plot_data),
        )

        queue.put(output)
    except Exception as e:
        logger.exception(
            f"Exception in celery worker during simulation initialization {e}"
        )
        queue.put(SimulationError(message=f"Simulation initialization failed {e}"))
    finally:
        logger.debug("Initialization of simulation done")
        return


CurrentSynapses = list[SynapseMetadata] | None
FrequencySynapses = dict[float, list[SynapseMetadata]] | None


def setup_synapses_series(
    cf: SingleNeuronSimulationConfig,
    synaptome_details: SynaptomeDetails | None,
    model: Model,
) -> tuple[CurrentSynapses, FrequencySynapses]:
    synapse_generation_config: CurrentSynapses = None
    frequency_to_synapse_config: FrequencySynapses = None

    if synaptome_details is None:
        return (None, None)

    if is_current_varying_simulation(cf):
        if cf.type == "synaptome-simulation" and cf.synaptome is not None:
            # only current injection simulation
            synapse_settings: list[list[SynapseMetadata]] = []
            for index, synapse_sim_config in enumerate(cf.synaptome):
                # 3. Get "pandas.Series" for each synapse
                synapse_placement_config = [
                    config
                    for config in synaptome_details.synaptome_placement_config.config
                    if synapse_sim_config.id == config.id
                ][0]

                assert not isinstance(synapse_sim_config.frequency, list)
                synapses_per_grp = model.get_synapse_series(
                    synapse_placement_config=synapse_placement_config,
                    synapse_simulation_config=synapse_sim_config,
                    offset=index,
                    frequencies_to_apply=[synapse_sim_config.frequency],
                )

                synapse_settings.append(synapses_per_grp)

            synapse_generation_config = list(chain.from_iterable(synapse_settings))
    else:
        assert cf.synaptome is not None

        variable_frequency_sim_configs: list[SynaptomeSimulationConfig] = []
        constant_frequency_sim_configs: list[SynaptomeSimulationConfig] = []
        # Split all incoming simulation configs into constant frequency or variable frequency sim configs
        for syn_sim_config in cf.synaptome:
            if isinstance(syn_sim_config.frequency, list):
                variable_frequency_sim_configs.append(syn_sim_config)
            else:
                constant_frequency_sim_configs.append(syn_sim_config)

        frequency_to_synapse_config = {}

        offset = 0
        for variable_frequency_sim_config in variable_frequency_sim_configs:
            synapse_placement_config = get_synapse_placement_config(
                variable_frequency_sim_config.id,
                synaptome_details.synaptome_placement_config,
            )
            assert isinstance(variable_frequency_sim_config.frequency, list)

            for frequency in variable_frequency_sim_config.frequency:
                frequency_to_synapse_config[frequency] = []

                frequencies_to_apply = get_constant_frequencies_for_sim_id(
                    variable_frequency_sim_config.id, constant_frequency_sim_configs
                )
                frequencies_to_apply.append(frequency)
                # First, add synapse_series for sim_config with this variable frequency
                frequency_to_synapse_config[frequency].extend(
                    model.get_synapse_series(
                        synapse_placement_config=synapse_placement_config,
                        synapse_simulation_config=variable_frequency_sim_config,
                        offset=offset,
                        frequencies_to_apply=frequencies_to_apply,
                    )
                )
                offset += 1

                sim_id_to_configs = get_sim_configs_by_synapse_id(
                    constant_frequency_sim_configs
                )

                # Second, add synapse series for other sim configs of same synapse_set, but which have constant frequencies
                if variable_frequency_sim_config.id in sim_id_to_configs:
                    for sim_config in sim_id_to_configs[
                        variable_frequency_sim_config.id
                    ]:
                        frequency_to_synapse_config[frequency].extend(
                            model.get_synapse_series(
                                synapse_placement_config=synapse_placement_config,
                                synapse_simulation_config=sim_config,
                                offset=offset,
                                frequencies_to_apply=frequencies_to_apply,
                            )
                        )
                        offset += 1
                    # Since all synapses for variable_frequency_sim_config are now added, remove it from the dictionary
                    sim_id_to_configs.pop(variable_frequency_sim_config.id)

                # Finally, add synapse series for all other sim configs from different synapse_sets (these should have constant frequencies)
                for index, sim_id in enumerate(sim_id_to_configs):
                    sim_configs_for_set = sim_id_to_configs[sim_id]
                    constant_frequencies_for_set = get_constant_frequencies_for_sim_id(
                        sim_id, sim_configs_for_set
                    )
                    placement_config_for_set = get_synapse_placement_config(
                        sim_id, synaptome_details.synaptome_placement_config
                    )

                    for sim_config in sim_configs_for_set:
                        frequency_to_synapse_config[frequency].extend(
                            model.get_synapse_series(
                                synapse_placement_config=placement_config_for_set,
                                synapse_simulation_config=sim_config,
                                offset=offset,
                                frequencies_to_apply=constant_frequencies_for_set,
                            )
                        )
                        offset += 1

        for frequency in frequency_to_synapse_config:
            logger.debug(
                f"Constructed {len(frequency_to_synapse_config[frequency])} synapse series for frequency {frequency}"
            )
            log_stats_for_series_in_frequency(frequency_to_synapse_config[frequency])

    return (
        synapse_generation_config,
        frequency_to_synapse_config,
    )
