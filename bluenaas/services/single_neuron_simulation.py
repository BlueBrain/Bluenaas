import asyncio
import json
import multiprocessing as mp
from itertools import chain
import time
from bluenaas.utils.streaming import (
    StreamingResponseWithCleanup,
    cleanup,
)
from bluenaas.utils.util import log_stats_for_series_in_frequency
from loguru import logger
from http import HTTPStatus as status
from fastapi.responses import StreamingResponse
from typing import Any, Optional

from queue import Empty as QueueEmptyException
from multiprocessing.synchronize import Event
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    SimulationError,
)
from bluenaas.core.model import fetch_synaptome_model_details
from bluenaas.domains.morphology import (
    SynapseConfig,
    SynapseSeries,
    SynapsesPlacementConfig,
)
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    SynapseSimulationConfig,
)
from bluenaas.utils.const import QUEUE_STOP_EVENT


def _init_current_varying_simulation(
    model_id: str,
    token: str,
    config: SingleNeuronSimulationConfig,
    realtime: bool,
    simulation_queue: mp.Queue,
    req_id: str,
    stop_event: Event,
):
    from bluenaas.core.model import model_factory

    try:
        me_model_id = model_id
        synapse_generation_config: list[SynapseSeries] = None

        if config.type == "synaptome-simulation" and config.synapses is not None:
            # and model.resource.type:
            synaptome_details = fetch_synaptome_model_details(
                synaptome_self=model_id, bearer_token=token
            )
            me_model_id = synaptome_details.base_model_self

        model = model_factory(
            model_id=me_model_id,
            hyamp=config.conditions.hypamp,
            bearer_token=token,
        )

        if config.type == "synaptome-simulation" and config.synapses is not None:
            # only current injection simulation
            synapse_settings: list[list[SynapseSeries]] = []
            for index, synapse_sim_config in enumerate(config.synapses):
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

        model.CELL.start_current_varying_simulation(
            realtime=realtime,
            config=config,
            synapse_generation_config=synapse_generation_config,
            simulation_queue=simulation_queue,
            req_id=req_id,
            stop_event=stop_event,
        )
    except SimulationError as ex:
        simulation_queue.put(ex)
        simulation_queue.put(QUEUE_STOP_EVENT)
        raise ex
    except Exception as ex:
        logger.exception(f"Simulation executor error: {ex}")
        raise SimulationError from ex
    finally:
        logger.info("Simulation executor ended")


def get_constant_frequencies_for_sim_id(
    synapse_set_id: str, constant_frequency_sim_configs: list[SynapseSimulationConfig]
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
    sim_configs: list[SynapseSimulationConfig],
) -> dict[str, list[SynapseSimulationConfig]]:
    sim_id_to_sim_configs: dict[str, list[SynapseSimulationConfig]] = {}

    for sim_config in sim_configs:
        if sim_config.id in sim_id_to_sim_configs:
            sim_id_to_sim_configs[sim_config.id].append(sim_config)
        else:
            sim_id_to_sim_configs[sim_config.id] = [sim_config]

    return sim_id_to_sim_configs


def _init_frequency_varying_simulation(
    model_id: str,
    token: str,
    config: SingleNeuronSimulationConfig,
    realtime: bool,
    simulation_queue: mp.Queue,
    req_id: str,
    stop_event: Event,
):
    from bluenaas.core.model import model_factory

    try:
        me_model_id = model_id
        synaptome_details = fetch_synaptome_model_details(
            synaptome_self=model_id, bearer_token=token
        )
        me_model_id = synaptome_details.base_model_self

        model = model_factory(
            model_id=me_model_id,
            hyamp=config.conditions.hypamp,
            bearer_token=token,
        )
        assert config.synapses is not None

        variable_frequency_sim_configs: list[SynapseSimulationConfig] = []
        constant_frequency_sim_configs: list[SynapseSimulationConfig] = []

        # Split all incoming simulation configs into constant frequency or variable frequency sim configs
        for syn_sim_config in config.synapses:
            if isinstance(syn_sim_config.frequency, list):
                variable_frequency_sim_configs.append(syn_sim_config)
            else:
                constant_frequency_sim_configs.append(syn_sim_config)

        frequency_to_synapse_settings: dict[float, list[SynapseSeries]] = {}

        offset = 0
        for variable_frequency_sim_config in variable_frequency_sim_configs:
            synapse_placement_config = get_synapse_placement_config(
                variable_frequency_sim_config.id,
                synaptome_details.synaptome_placement_config,
            )

            for frequency in variable_frequency_sim_config.frequency:
                frequency_to_synapse_settings[frequency] = []

                frequencies_to_apply = get_constant_frequencies_for_sim_id(
                    variable_frequency_sim_config.id, constant_frequency_sim_configs
                )
                frequencies_to_apply.append(frequency)

                # First, add synapse_series for sim_config with this variable frequency
                frequency_to_synapse_settings[frequency].extend(
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
                        frequency_to_synapse_settings[frequency].extend(
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
                        frequency_to_synapse_settings[frequency].extend(
                            model.get_synapse_series(
                                placement_config_for_set,
                                sim_config,
                                offset,
                                constant_frequencies_for_set,
                            )
                        )
                        offset += 1

        for frequency in frequency_to_synapse_settings:
            logger.debug(
                f"Constructed {len(frequency_to_synapse_settings[frequency])} synapse series for frequency {frequency}"
            )
            log_stats_for_series_in_frequency(frequency_to_synapse_settings[frequency])

        model.CELL.start_frequency_varying_simulation(
            config=config,
            frequency_to_synapse_series=frequency_to_synapse_settings,
            simulation_queue=simulation_queue,
            req_id=req_id,
            stop_event=stop_event,
        )
    except SimulationError as ex:
        logger.exception(f"Simulation executor error: {ex}")
        simulation_queue.put(ex)
        simulation_queue.put(QUEUE_STOP_EVENT)
        raise ex
    except Exception as ex:
        logger.exception(f"Simulation executor error: {ex}")
        raise SimulationError from ex
    finally:
        logger.info("Simulation executor ended")


def is_current_varying_simulation(config: SingleNeuronSimulationConfig) -> bool:
    if config.type == "single-neuron-simulation" or config.synapses is None:
        return True

    synapse_set_with_multiple_frequency = [
        synapse_set
        for synapse_set in config.synapses
        if isinstance(synapse_set.frequency, list)
    ]
    if len(synapse_set_with_multiple_frequency) > 0:
        # TODO: This assertion should be at pydantic model level
        assert not isinstance(config.current_injection.stimulus.amplitudes, list)
        return False

    return True


def execute_single_neuron_simulation(
    org_id: str,
    project_id: str,
    model_id: str,
    token: str,
    config: SingleNeuronSimulationConfig,
    req_id: str,
    realtime: bool,
    simulation_resource_id: Optional[str] = None,
):
    try:
        ctx = mp.get_context("spawn")
        stop_event = ctx.Event()
        simulation_queue = ctx.Queue()

        is_current_varying = is_current_varying_simulation(config)

        _process = ctx.Process(
            target=_init_current_varying_simulation
            if is_current_varying
            else _init_frequency_varying_simulation,
            args=(
                model_id,
                token,
                config,
                realtime,
                simulation_queue,
                req_id,
                stop_event,
            ),
            name=f"simulation_processor:{req_id}",
        )

        _process.start()

        if realtime is True:

            def queue_streamify():
                while True:
                    try:
                        # Simulation_Queue.get() is blocking. If child fails without writing to it,
                        # the process will hang forever. That's why timeout is added.
                        record = simulation_queue.get(timeout=1)
                    except QueueEmptyException:
                        if _process.is_alive():
                            continue
                        else:
                            logger.warning(
                                "Process is not alive and simulation queue is empty"
                            )
                            raise Exception("Child process died unexpectedly")
                    if isinstance(record, SimulationError):
                        yield f"{json.dumps(
                            {
                                "error_code": BlueNaasErrorCode.SIMULATION_ERROR,
                                "message": "Simulation failed",
                                "details": record.__str__(),
                            }
                        )}\n"
                        logger.debug("Parent stopping because of error")
                        break
                    if record == QUEUE_STOP_EVENT:
                        logger.debug("Parent received queue_stop_event")
                        break

                    if is_current_varying:
                        # (stimulus_name, recording_name, amplitude, recording) = record

                        logger.info(
                            f"[R/S --> {record["label"]}/{record["recording_name"]}]",
                        )
                        yield f"{json.dumps(
                            {
                                "amplitude": record["amplitude"],
                                "label": record["label"],
                                "recording_name": record["recording_name"],
                                "t": record["time"],
                                "v": record["voltage"],
                                "varying_key": record["amplitude"]
                            }
                        )}\n"
                    else:
                        logger.info(
                            f"Frequency [R/S --> {record["label"]}/{record["recording_name"]}]",
                        )
                        yield f"{json.dumps(
                            {
                                "frequency": record["frequency"],
                                "label": record["label"],
                                "recording_name": record["recording_name"],
                                "t": record["time"],
                                "v": record["voltage"],
                                "varying_key": record["frequency"]
                            }
                        )}\n"

                logger.info(f"Simulation {req_id} completed")

            return StreamingResponseWithCleanup(
                queue_streamify(),
                media_type="application/octet-stream",
                finalizer=lambda: cleanup(stop_event, _process),
            )

        else:
            final_result: dict[str, Any] = {}
            while True:
                try:
                    # Simulation_Queue.get() is blocking. If child fails without writing to it,
                    # the process will hang forever. That's why timeout is added.
                    record = simulation_queue.get(timeout=1)
                except QueueEmptyException:
                    if _process.is_alive():
                        continue
                    else:
                        logger.warning(
                            "Process is not alive and simulation queue is empty"
                        )
                        raise Exception("Child process died unexpectedly")
                if isinstance(record, SimulationError):
                    # TODO: Update simulation state to error
                    logger.debug("Parent stopping because of error")
                    break
                if record == QUEUE_STOP_EVENT:
                    logger.debug("Parent received queue_stop_event")
                    break

                if is_current_varying:
                    # (stimulus_name, recording_name, amplitude, recording) = record
                    recording_name = record["recording_name"]
                    logger.info(
                        f"[R/S --> {record["label"]}/{recording_name}]",
                    )

                    current_recording_data = (
                        final_result[recording_name]
                        if recording_name in final_result
                        else []
                    )
                    current_recording_data.append(
                        {
                            "x": record["time"],
                            "y": record["voltage"],
                            "type": "scatter",
                            "name": record["label"],
                            "recording": recording_name,
                            "amplitude": record["amplitude"],
                            "frequency": None,
                            "varying_key": record["amplitude"],
                        }
                    )
                else:
                    logger.info(
                        f"Frequency [R/S --> {record["label"]}/{record["recording_name"]}]",
                    )
                    current_recording_data.append(
                        {
                            "x": record["time"],
                            "y": record["voltage"],
                            "type": "scatter",
                            "name": record["label"],
                            "recording": recording_name,
                            "amplitude": None,
                            "frequency": record["frequency"],
                            "varying_key": record["frequency"],
                        }
                    )

            # TODO: Save final result

    except Exception as ex:
        logger.exception(f"running simulation failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="running simulation failed",
            details=ex.__str__(),
        ) from ex
