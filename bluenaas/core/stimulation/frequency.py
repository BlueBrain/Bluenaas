# TODO: IMPORTANT: This methods is replicated from BlueCellab and any changes from the library should be updated here too

from __future__ import annotations
from typing import Any
from loguru import logger
from bluenaas.core.stimulation.utils import add_single_synapse
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


def _run_frequency_varying_stimulus(
    template_params,
    stimulus,
    injection_section_name: str,
    injection_segment: float,
    recording_locations: list[RecordingLocation],
    synapse_generation_config: list[SynapseSeries] | None,
    experimental_setup: ExperimentSetupConfig,
    simulation_duration: int,
    amplitude: float,
    frequency: float,
    add_hypamp: bool = True,
    enable_realtime: bool = True,
    queue: Any | None = None,
):
    logger.info(f"""
        [frequency]: {frequency}
        [enable_realtime]: {enable_realtime}
        [simulation stimulus/start]: {stimulus}
        [simulation injection_section_name (provided)]: {injection_section_name}
        [simulation recording_locations]: {recording_locations}
    """)

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
        frequency,
        "frequency",
        "Frequency",
        enable_realtime,
    )


def apply_multiple_frequency(
    cell,
    current_injection: CurrentInjectionConfig,
    recording_locations: list[RecordingLocation],
    experiment_setup: ExperimentSetupConfig,
    simulation_duration: int,
    frequency_to_synapse_series: dict[float, list[SynapseSeries]],
    enable_realtime: bool = True,
):
    logger.info(f"""
        Running Simulation With Frequencies of:
        {"CurrentInjection" if current_injection is not None else ""}
        {"Synaptome"}
    """)

    logger.info(f"[simulation duration]: {simulation_duration}")

    args = prepare_stimulation_parameters(
        cell=cell,
        current_injection=current_injection,
        recording_locations=recording_locations,
        frequency_to_synapse_series=frequency_to_synapse_series,
        current_synapse_series=None,
        conditions=experiment_setup,
        simulation_duration=simulation_duration,
        varying_type="frequency",
        enable_realtime=enable_realtime,
    )

    logger.debug(f"Applying simulation for {len(args)} frequencies")

    return apply_multiple_simulations(
        args=args,
        runner=_run_frequency_varying_stimulus,
    )
