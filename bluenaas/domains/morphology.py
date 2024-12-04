from typing import List, Literal, Optional, TypedDict
from pydantic import BaseModel, field_validator
import sympy as sp  # type: ignore
import pandas  # type: ignore
from enum import Enum

from bluenaas.domains.simulation import (
    CurrentInjectionConfig,
    SynaptomeSimulationConfig,
)


class LocationData(BaseModel):
    index: int
    nseg: int
    xstart: List[float]
    xend: List[float]
    xcenter: List[float]
    xdirection: List[float]
    ystart: List[float]
    yend: List[float]
    ycenter: List[float]
    ydirection: List[float]
    zstart: List[float]
    zend: List[float]
    zcenter: List[float]
    zdirection: List[float]
    segx: List[float]
    diam: List[float]
    length: List[float]
    distance: List[float]
    distance_from_soma: float
    sec_length: float
    neuron_segments_offset: List[float]
    neuron_section_id: int
    segment_distance_from_soma: list[float]


class SectionTarget(Enum):
    apical = "apic"
    basal = "basal"
    dendrite = "dend"
    soma = "soma"
    axon = "axon"

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


class ExclusionRule(BaseModel):
    distance_soma_gte: float | None = None
    distance_soma_lte: float | None = None


class SynapseConfig(BaseModel):
    id: str
    name: str
    target: SectionTarget | None = None
    type: int
    distribution: Literal["exponential", "linear", "formula"] | None = None
    formula: Optional[str | None] = None
    soma_synapse_count: int | None = None
    seed: int
    exclusion_rules: list[ExclusionRule] | None = None

    @field_validator("soma_synapse_count")
    @classmethod
    def validate_soma_synapse_count(cls, value, info):
        if "target" in info.data and info.data.get("target") == SectionTarget.soma:
            if not value:
                raise ValueError(
                    "soma_section_count should be provided if target is soma"
                )

            if value < 0 or value > 1000:
                raise ValueError(
                    "soma_section_count should be greater than 0 and less than or equal to 1000"
                )
        return value

    @field_validator("formula", mode="before")
    @classmethod
    def validate_formula_depends_on_distribution(cls, value, info):
        if "distribution" in info.data and info.data.get("distribution") == "formula":
            if not value or not isinstance(value, str):
                raise ValueError(
                    'Formula must be a valid string when distribution is "formula".'
                )

            try:
                expr = sp.sympify(value)
                # Check if all free symbols are 'x' or 'X'
                allowed_symbols = {"x", "X"}
                free_symbols = {str(symbol) for symbol in expr.free_symbols}
                if not free_symbols.issubset(allowed_symbols):
                    raise ValueError("Formula can only contain the variable x or X.")

            except (sp.SympifyError, TypeError) as ex:
                raise ValueError(
                    f"Formula must be a valid mathematical expression. {ex}"
                )

        return value


# TODO: Remove
class SynapsePlacementBody(BaseModel):
    seed: int
    config: SynapseConfig


class SynapsesPlacementConfig(BaseModel):
    seed: int
    config: list[SynapseConfig]


class SynapsePosition(BaseModel):
    segment_id: int
    coordinates: list[float]
    position: float


class SectionSynapses(BaseModel):
    section_id: str
    synapses: list[SynapsePosition]


class SynapsePlacementResponse(BaseModel):
    synapses: list[SectionSynapses]


SynapseSeries = TypedDict(
    "SynapseSeries",
    {
        "id": int,
        "series": pandas.Series,
        "directCurrentConfig": CurrentInjectionConfig,
        "synapseSimulationConfig": SynaptomeSimulationConfig,
        "frequencies_to_apply": list[float],
    },
)


class SynapseMetadata(BaseModel):
    id: int
    section_info: LocationData
    segment_indices: list[int]
    type: int  # Inhibitory or exhibitory
    simulation_config: SynaptomeSimulationConfig
    frequencies_to_apply: list[float]
