from datetime import datetime
from typing import Annotated, Any, List, TypedDict
from pydantic import BaseModel, Field
from bluenaas.domains.simulation import (
    SimulationStatus,
    SingleNeuronSimulationConfig,
    StimulationItemResponse,
)


class NexusBaseResource(BaseModel):
    context: Annotated[str | List[Any], Field(alias="@context")] = []
    id: Annotated[str, Field(alias="@id")]
    type: Annotated[str | List[str] | None, Field(alias="@type")] = None
    createdAt: Annotated[datetime, Field(alias="_createdAt")]
    createdBy: Annotated[str, Field(alias="_createdBy")]
    deprecated: Annotated[bool, Field(alias="_deprecated")]
    self: Annotated[str, Field(alias="_self")]
    rev: Annotated[int, Field(alias="_rev")]


NexusUsed = TypedDict(
    "NexusUsed",
    {
        "@type": list[str] | str,
        "@id": str,
    },
)

CreatedNexusResource = TypedDict(
    "CreatedNexusResource", {"source": dict, "metadata": dict}
)


class NexusSimulationPayload(BaseModel):
    simulation: Any
    stimulus: list[StimulationItemResponse]
    config: SingleNeuronSimulationConfig


class BaseNexusSimulationResource(BaseModel):
    type: Annotated[str | List[str], Field(alias="@type")]
    context: Annotated[str, Field(alias="@context")]

    name: str
    description: str
    used: NexusUsed
    distribution: list[dict[str, Any]] | dict[str, Any]
    injectionLocation: str
    recordingLocation: list[str] | str
    brainLocation: Any  # TODO Add better type
    isDraft: bool | None = None
    status: str | None = None  # TODO Add better type

    class Config:
        populate_by_name = True


class FullNexusSimulationResource(NexusBaseResource):
    name: str
    description: str
    used: NexusUsed
    distribution: list[dict[str, Any]] | dict[str, Any]
    injectionLocation: str
    recordingLocation: list[str] | str
    brainLocation: Any  # TODO Add better type
    is_draft: bool | None = None
    status: SimulationStatus | None = None
    error: str | None = None

    class Config:
        populate_by_name = True


class DeprecateNexusResponse(BaseModel):
    id: str
    deprecated: bool
    updated_at: datetime
