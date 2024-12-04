from __future__ import annotations
import numpy as np
from typing import Dict, NamedTuple
from enum import Enum, auto
import pandas  # type: ignore
from random import random, randint
from bluenaas.domains.morphology import (
    SynapseConfig,
    SynapsesPlacementConfig,
    LocationData,
    SynapseMetadata,
)
from bluenaas.domains.simulation import (
    ExperimentSetupConfig,
    SingleNeuronSimulationConfig,
    SynaptomeSimulationConfig,
)
from bluenaas.utils.util import generate_pre_spiketrain


class Recording(NamedTuple):
    """A tuple of the current, voltage and time recordings."""

    current: np.ndarray
    voltage: np.ndarray
    time: np.ndarray


class SynapseRecording(NamedTuple):
    """A tuple of the current, voltage and time recordings."""

    voltage: np.ndarray
    time: np.ndarray


class StimulusName(Enum):
    """Allowed values for the StimulusName."""

    AP_WAVEFORM = auto()
    IDREST = auto()
    IV = auto()
    FIRE_PATTERN = auto()
    POS_CHEOPS = auto()
    NEG_CHEOPS = auto()


StimulusRecordings = Dict[str, Recording]


def _get_pandas_series_for_section(
    section_info: LocationData,
    seg_indices_to_include: list[int],
    synapse_type: int,
    simulation_config: SynaptomeSimulationConfig,
):
    from bluecellulab.circuit.synapse_properties import SynapseProperty  # type: ignore

    random_index = randint(0, len(seg_indices_to_include) - 1)
    target_segment = seg_indices_to_include[random_index]

    position = random()
    # 1. get the seg_x for target segment
    start = section_info.neuron_segments_offset[target_segment]
    # 2. get the seg_x for target segment +1
    end = section_info.neuron_segments_offset[target_segment + 1]
    diff = end - start
    offset = position * diff
    # 3. if the offset is bind to the section id not segment id then
    # offset = (position * diff) + start

    syn_description = pandas.Series(
        {
            SynapseProperty.PRE_GID: 1,
            SynapseProperty.AXONAL_DELAY: 1.0,
            SynapseProperty.G_SYNX: simulation_config.weight_scalar,
            SynapseProperty.TYPE: synapse_type,
            SynapseProperty.U_SYN: 0.505514,
            SynapseProperty.D_SYN: 684.279663,
            SynapseProperty.F_SYN: 1.937531,
            SynapseProperty.DTC: 2.983491,
            # SynapseProperty.NRRP: 2,
            # "source_population_name": "hippocampus_projections",
            # "source_popid": 2126,
            # "target_popid": 378,
            # SynapseProperty.AFFERENT_SECTION_POS: 0.365956,
            SynapseProperty.POST_SECTION_ID: section_info.neuron_section_id,
            SynapseProperty.POST_SEGMENT_ID: target_segment,
            SynapseProperty.POST_SEGMENT_OFFSET: offset,
        }
    )
    return syn_description


def add_single_synapse(
    cell,
    synapse: SynapseMetadata,
    experimental_setup: ExperimentSetupConfig,
):
    from bluecellulab.circuit.config.sections import Conditions  # type: ignore
    from bluecellulab.synapse.synapse_types import SynapseID  # type: ignore
    from bluecellulab import Connection  # type: ignore

    condition_parameters = Conditions(
        celsius=experimental_setup.celsius,
        v_init=experimental_setup.vinit,
        randomize_gaba_rise_time=True,
    )
    synid = SynapseID(f"{synapse.id}", synapse.id)
    # A tuple containing source and target popids used by the random number generation.
    # Should correspond to source_popid and target_popid
    # TODO: remove `popids` if not needed
    popids = (2126, 378)
    connection_modifiers = {
        "add_synapses": True,
    }

    cell.add_replay_synapse(
        synapse_id=synid,
        syn_description=_get_pandas_series_for_section(
            section_info=synapse.section_info,
            seg_indices_to_include=synapse.segment_indices,
            synapse_type=synapse.type,
            simulation_config=synapse.simulation_config,
        ),
        connection_modifiers=connection_modifiers,
        condition_parameters=condition_parameters,
        popids=popids,
        extracellular_calcium=None,  # may not be value used in circuit
    )
    cell_synapse = cell.synapses[synid]

    spike_train = generate_pre_spiketrain(
        duration=synapse.simulation_config.duration,
        delay=synapse.simulation_config.delay,
        frequencies=synapse.frequencies_to_apply,
    )
    # TODO: remove `spike_threshold` default value is -30 and that's fine
    spike_threshold = -900.0  # TODO: Synapse - How to get spike threshold
    connection = Connection(
        cell_synapse,
        pre_spiketrain=spike_train,
        pre_cell=None,
        stim_dt=cell.record_dt,
        spike_threshold=spike_threshold,
        spike_location="soma[0]",
    )
    cell.connections[synid] = connection


def is_valid_stimuls_result(value):
    """Checks if the given value is a tuple of (str, Recording).

    Args:
      value: The value to check.

    Returns:
      True if the value is a valid tuple, False otherwise.
    """

    if not isinstance(value, tuple) or len(value) != 2:
        return False

    key, recording = value
    return isinstance(key, str) and isinstance(recording, Recording)


def get_stimulus_name(protocol_name):
    protocol_mapping = {
        "ap_waveform": StimulusName.AP_WAVEFORM,
        "idrest": StimulusName.IDREST,
        "iv": StimulusName.IV,
        "fire_pattern": StimulusName.FIRE_PATTERN,
    }

    if protocol_name not in protocol_mapping:
        raise Exception("Protocol does not have StimulusName assigned")

    return protocol_mapping[protocol_name]


def init_process_worker(neuron_global_params):
    """Load global parameters for the NEURON environment in each worker
    process."""
    from bluecellulab.simulation.neuron_globals import NeuronGlobals  # type: ignore

    NeuronGlobals.get_instance().load_params(neuron_global_params)


def get_stimulus_from_name(
    stimulus_name: StimulusName, stimulus_factory, cell, thres_perc, amp
):
    if stimulus_name == StimulusName.AP_WAVEFORM:
        return stimulus_factory.ap_waveform(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )
    elif stimulus_name == StimulusName.IDREST:
        return stimulus_factory.idrest(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )
    elif stimulus_name == StimulusName.IV:
        return stimulus_factory.iv(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )
    elif stimulus_name == StimulusName.FIRE_PATTERN:
        return stimulus_factory.fire_pattern(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )
    elif stimulus_name == StimulusName.POS_CHEOPS:
        return stimulus_factory.pos_cheops(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )
    elif stimulus_name == StimulusName.NEG_CHEOPS:
        return stimulus_factory.neg_cheops(
            threshold_current=cell.threshold,
            threshold_percentage=thres_perc,
            amplitude=amp,
        )


def get_constant_frequencies_for_sim_id(
    synapse_set_id: str, constant_frequency_sim_configs: list[SynaptomeSimulationConfig]
):
    constant_frequencies: list[float] = []
    for sim_config in constant_frequency_sim_configs:
        if sim_config.id == synapse_set_id and not isinstance(
            sim_config.frequency, list
        ):
            constant_frequencies.append(sim_config.frequency)

    return constant_frequencies


def get_synapse_placement_config(
    sim_id: str, placement_configs: SynapsesPlacementConfig
) -> SynapseConfig:
    for placement_config in placement_configs.config:
        if placement_config.id == sim_id:
            return placement_config

    raise Exception(f"No synaptome placement config was found with id {sim_id}")


def get_sim_configs_by_synapse_id(
    sim_configs: list[SynaptomeSimulationConfig],
) -> dict[str, list[SynaptomeSimulationConfig]]:
    sim_id_to_sim_configs: dict[str, list[SynaptomeSimulationConfig]] = {}

    for sim_config in sim_configs:
        if sim_config.id in sim_id_to_sim_configs:
            sim_id_to_sim_configs[sim_config.id].append(sim_config)
        else:
            sim_id_to_sim_configs[sim_config.id] = [sim_config]

    return sim_id_to_sim_configs


def is_current_varying_simulation(config: SingleNeuronSimulationConfig) -> bool:
    if config.type == "single-neuron-simulation" or config.synaptome is None:
        return True

    synapse_set_with_multiple_frequency = [
        synapse_set
        for synapse_set in config.synaptome
        if isinstance(synapse_set.frequency, list)
    ]
    if len(synapse_set_with_multiple_frequency) > 0:
        # TODO: This assertion should be at pydantic model level
        assert not isinstance(config.current_injection.stimulus.amplitudes, list)
        return False

    return True
