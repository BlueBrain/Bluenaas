from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, PositiveInt, field_validator


class SimulationStimulusConfig(BaseModel):
    stimulusType: Literal["current_clamp", "voltage_clamp", "conductance"]
    stimulusProtocol: Optional[Literal["ap_waveform", "idrest", "iv", "fire_pattern"]]
    amplitudes: List[float]


class RecordingLocation(BaseModel):
    section: str
    offset: Annotated[float, Field(ge=0, le=1)]


class CurrentInjectionConfig(BaseModel):
    injectTo: str
    stimulus: SimulationStimulusConfig


class SimulationConditionsConfig(BaseModel):
    celsius: float
    vinit: float
    hypamp: float
    max_time: float | None


class SynapseSimulationConfig(BaseModel):
    id: str
    delay: int
    duration: int
    frequency: PositiveInt
    weightScalar: int


class SimulationWithSynapseBody(BaseModel):
    directCurrentConfig: CurrentInjectionConfig
    synapseConfigs: list[SynapseSimulationConfig]


SimulationType = Literal["single-neuron-simulation", "synaptome-simulation"]
class SingleNeuronSimulationConfig(BaseModel):
    currentInjection: CurrentInjectionConfig | None = None
    recordFrom: list[RecordingLocation]
    conditions: SimulationConditionsConfig
    synapses: list[SynapseSimulationConfig] | None = None
    type: SimulationType

    # @field_validator("synapses", mode="before")
    # @classmethod
    # def validate_current_injection_synapses(cls, value, info):
    #     if ("synapses" not in info.data or info.data.get("synapses") is None) and (
    #         "currentInjection" not in info.data
    #         or info.data.get("currentInjection") is None
    #     ):
    #         raise ValueError(
    #             "Neither synapses nor current injection configuration are provided"
    #         )

    #     return value


class StimulationPlotConfig(BaseModel):
    stimulusProtocol: Optional[Literal["ap_waveform", "idrest", "iv", "fire_pattern"]]
    amplitudes: List[int]


class SimulationItemResponse(BaseModel):
    t: List[float] = Field(..., description="Time points")
    v: List[float] = Field(..., description="Voltage points")
    name: str = Field(..., description="Name of the stimulus")


class StimulationItemResponse(BaseModel):
    x: List[int]
    y: List[float]
    name: str