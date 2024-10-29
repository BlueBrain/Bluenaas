from __future__ import annotations
import os
from typing import Any
from loguru import logger
from bluenaas.core.stimulation.utils import (
    StimulusName,
    add_single_synapse,
)
from bluenaas.core.stimulation.common import (
    prepare_stimulation_parameters,
    apply_multiple_simulations,
    basic_simulation_config,
    dispatch_simulation_result,
)
from bluenaas.domains.morphology import SynapseSeries
from bluenaas.domains.simulation import (
    CurrentInjectionConfig,
    RecordingLocation,
    ExperimentSetupConfig,
)


def _run_current_varying_stimulus(
    template_params,
    stimulus,
    injection_section_name: str,
    injection_segment: float,
    recording_locations: list[RecordingLocation],
    synapse_generation_config: list[SynapseSeries] | None,
    experimental_setup: ExperimentSetupConfig,
    simulation_duration: int,
    stimulus_name: StimulusName,
    amplitude: float,
    add_hypamp: bool = True,
    enable_realtime: bool = True,
    queue: Any | None = None,
):
    logger.info(f"""
        [enable_realtime]: {enable_realtime}
        [simulation stimulus/start]: {stimulus}
        [simulation injection_section_name (provided)]: {injection_section_name}
        [simulation recording_locations]: {recording_locations}
    """)
    cwd = os.getcwd()
    logger.info(f"@@@@-> {cwd=}")
    (cell, current) = basic_simulation_config(
        template_params,
        stimulus,
        injection_section_name,
        injection_segment,
        recording_locations,
        experimental_setup,
        add_hypamp,
    )

    if synapse_generation_config is not None:
        for synapse in synapse_generation_config:
            # Frequency should be constant in current varying simulation
            # TODO: handle AssertionError in the upper function
            assert isinstance(synapse["synapseSimulationConfig"].frequency, float)
            add_single_synapse(
                cell=cell,
                synapse=synapse,
                experimental_setup=experimental_setup,
            )

    return dispatch_simulation_result(
        cell,
        queue,
        current,
        recording_locations,
        simulation_duration,
        experimental_setup.time_step,
        amplitude,
        None,
        "current",
        stimulus_name.name,
        enable_realtime,
    )


def apply_multiple_stimulus(
    cell,
    current_injection: CurrentInjectionConfig,
    recording_locations: list[RecordingLocation],
    experiment_setup: ExperimentSetupConfig,
    simulation_duration: int,
    current_synapse_series: list[SynapseSeries] | None,
    enable_realtime: bool = True,
):
    logger.info(f"""
        Running Simulation enable_realtime {enable_realtime} of:
        {"CurrentInjection" if current_injection is not None else ""}
        {"Synaptome " if current_synapse_series is not None else ""}
    """)

    args = prepare_stimulation_parameters(
        cell=cell,
        current_injection=current_injection,
        recording_locations=recording_locations,
        frequency_to_synapse_series=None,
        current_synapse_series=current_synapse_series,
        conditions=experiment_setup,
        simulation_duration=simulation_duration,
        varying_type="current",
        enable_realtime=enable_realtime,
    )

    return apply_multiple_simulations(
        args=args,
        runner=_run_current_varying_stimulus,
    )
