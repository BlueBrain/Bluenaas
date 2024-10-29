from datetime import datetime
from typing import Annotated, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field, PositiveFloat, field_validator


SimulationType = Literal["single-neuron-simulation", "synaptome-simulation"]
NexusSimulationType = Literal["SingleNeuronSimulation", "SynaptomeSimulation"]

SimulationStatus = Literal["pending", "started", "success", "failure"]
SimulationEvent = Literal["init", "info", "data", "error"]
SimulationStreamData = TypedDict(
    "SimulationStreamData",
    {
        "label": str,
        "amplitude": str,
        "frequency": str,
        "recording": str,
        "varying_key": str,
        "t": list[float],
        "v": list[float],
    },
)

SIMULATION_TYPE_MAP: dict[NexusSimulationType, SimulationType] = {
    "SingleNeuronSimulation": "single-neuron-simulation",
    "SynaptomeSimulation": "synaptome-simulation",
}


class SimulationStimulusConfig(BaseModel):
    stimulus_type: Literal["current_clamp", "voltage_clamp", "conductance"]
    stimulus_protocol: Optional[Literal["ap_waveform", "idrest", "iv", "fire_pattern"]]
    amplitudes: list[float] | float

    @field_validator("amplitudes")
    @classmethod
    def validate_amplitudes(cls, value):
        if isinstance(value, list):
            if len(value) < 1 or len(value) > 15:
                raise ValueError(
                    "Amplitude length should be between 1 and 15 (inclusive)"
                )

        return value


class RecordingLocation(BaseModel):
    section: str
    offset: Annotated[float, Field(ge=0, le=1)]


class CurrentInjectionConfig(BaseModel):
    inject_to: str
    stimulus: SimulationStimulusConfig


class ExperimentSetupConfig(BaseModel):
    celsius: float
    vinit: float
    hypamp: float
    max_time: Annotated[float, Field(le=3000)]
    time_step: float
    seed: int


class SynaptomeSimulationConfig(BaseModel):
    id: str
    delay: int
    duration: Annotated[int, Field(le=3000)]
    frequency: PositiveFloat | list[PositiveFloat]
    weight_scalar: PositiveFloat


class SimulationWithSynapseBody(BaseModel):
    direct_current_config: CurrentInjectionConfig
    synapse_configs: list[SynaptomeSimulationConfig]


class SingleNeuronSimulationConfig(BaseModel):
    synaptome: list[SynaptomeSimulationConfig] | None = Field(
        alias="synaptome", default=None
    )
    current_injection: CurrentInjectionConfig
    record_from: list[RecordingLocation]
    conditions: ExperimentSetupConfig
    type: SimulationType = None
    duration: int = None

    @field_validator("current_injection")
    @classmethod
    def validate_amplitudes(cls, value, simulation):
        config = simulation.data

        if isinstance(value.stimulus.amplitudes, list):
            synapses = config.get("synapses") or []
            for synapse in synapses:
                if isinstance(synapse.frequency, list):
                    raise ValueError(
                        "Amplitude should be a constant float if frequency is a list"
                    )
        elif isinstance(value.stimulus.amplitudes, float):
            synapses = config.get("synapses") or []
            synapses_with_variable_frequencies = [
                synapse for synapse in synapses if isinstance(synapse.frequency, list)
            ]
            if len(synapses_with_variable_frequencies) != 1:
                raise ValueError(
                    f"There should be exactly one synapse with variable frequencies when amplitude is constant. Current synapses with variable frequencies: {len(synapses_with_variable_frequencies)}"
                )

        return value

    class Config:
        populate_by_name = True


class StimulationPlotConfig(BaseModel):
    stimulus_protocol: Optional[Literal["ap_waveform", "idrest", "iv", "fire_pattern"]]
    amplitudes: List[float]


class SimulationItemResponse(BaseModel):
    t: List[float] = Field(..., description="Time points")
    v: List[float] = Field(..., description="Voltage points")
    name: str = Field(..., description="Name of the stimulus")


class StimulationItemResponse(BaseModel):
    x: List[float]
    y: List[float]
    name: str
    amplitude: float


class SimulationBody(BaseModel):
    modelId: str = Field(..., alias="model_id")
    reqId: str = Field(..., alias="req_id")
    config: SingleNeuronSimulationConfig
    simulations: str

    class Config:
        populate_by_name = True


class PlotDataEntry(BaseModel):
    x: List[float]
    y: List[float]
    name: str
    amplitude: Optional[float]
    frequency: Optional[float]


class SimulationResultItemResponse(BaseModel):
    id: str
    self_uri: str
    status: SimulationStatus | None = None
    results: Optional[dict]

    type: SimulationType
    name: str
    description: str
    created_by: str
    created_at: datetime
    injection_location: str
    recording_location: list[str] | str
    brain_location: dict
    config: Optional[SingleNeuronSimulationConfig]

    me_model_self: str
    synaptome_model_self: Optional[str]
    job_id: Optional[str] = None

    def __getitem__(self, key):
        return getattr(self, key)


class PaginatedSimulationsResponse(BaseModel):
    page_offset: int
    page_size: int
    total: int
    results: list[SimulationResultItemResponse]


class StreamSimulationBodyRequest(BaseModel):
    config: SingleNeuronSimulationConfig
    autosave: Optional[bool] = False
    realtime: Optional[bool] = False


class StreamSimulationResponse(BaseModel):
    event: SimulationEvent
    state: SimulationStatus
    task_id: str
    description: str
    data: SimulationStreamData
