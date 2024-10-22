from itertools import chain
import json
from loguru import logger


from bluenaas.core.model import Model, SynaptomeDetails, fetch_synaptome_model_details
from bluenaas.core.stimulation.utils import (
    get_constant_frequencies_for_sim_id,
    get_sim_configs_by_synapse_id,
    get_synapse_placement_config,
    is_current_varying_simulation,
)
from bluenaas.infrastructure.celery import celery_app
from bluenaas.domains.morphology import SynapseSeries
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    SynaptomeSimulationConfig,
)
from bluenaas.utils.serializer import (
    serialize_synapse_series_dict,
    serialize_synapse_series_list,
    serialize_template_params,
)
from bluenaas.utils.util import log_stats_for_series_in_frequency


# NOTE: this is separation for worker queue is just for testing
# TODO: please remove it later
@celery_app.task(
    bind=True,
    serializer="json",
    queue="builder",
)
def initiate_simulation(
    self,
    model_self: str,
    token: str,
    config: SingleNeuronSimulationConfig,
):
    logger.info("[initiate simulation]")
    from bluenaas.core.model import model_factory

    cf = SingleNeuronSimulationConfig(**json.loads(config))
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

    (synapse_generation_config, frequency_to_synapse_config) = setup_synapses_series(
        cf,
        synaptome_details,
        model,
    )

    output = (
        me_model_id,
        serialize_template_params(template_params),
        serialize_synapse_series_list(synapse_generation_config)
        if synapse_generation_config is not None
        else None,
        serialize_synapse_series_dict(frequency_to_synapse_config)
        if frequency_to_synapse_config is not None
        else None,
    )
    logger.info(f"[INITIATE SIMULATION] {output=}")

    return output


def setup_synapses_series(
    cf: SingleNeuronSimulationConfig,
    synaptome_details: SynaptomeDetails | None,
    model: Model,
) -> tuple[list[SynapseSeries] | None, dict[float, list[SynapseSeries]] | None]:
    synapse_generation_config: list[SynapseSeries] = None
    frequency_to_synapse_config: dict[float, list[SynapseSeries]] = {}

    if synaptome_details is None:
        return (None, None)

    if is_current_varying_simulation(cf):
        if cf.type == "synaptome-simulation" and cf.synaptome is not None:
            # only current injection simulation
            synapse_settings: list[list[SynapseSeries]] = []
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

        frequency_to_synapse_config: dict[float, list[SynapseSeries]] = {}

        offset = 0
        for variable_frequency_sim_config in variable_frequency_sim_configs:
            synapse_placement_config = get_synapse_placement_config(
                variable_frequency_sim_config.id,
                synaptome_details.synaptome_placement_config,
            )

            for frequency in variable_frequency_sim_config.frequency:
                frequency_to_synapse_config[frequency] = []

                frequencies_to_apply = get_constant_frequencies_for_sim_id(
                    variable_frequency_sim_config.id, constant_frequency_sim_configs
                )
                frequencies_to_apply.append(frequency)

                # First, add synapse_series for sim_config with this variable frequency
                frequency_to_synapse_config[frequency].extend(
                    model.get_synapse_series(
                        synapse_placement_config,
                        variable_frequency_sim_config,
                        offset,
                        frequencies_to_apply,
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
                                synapse_placement_config,
                                sim_config,
                                offset,
                                frequencies_to_apply,
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
                                placement_config_for_set,
                                sim_config,
                                offset,
                                constant_frequencies_for_set,
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
