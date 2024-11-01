from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

from bluenaas.domains.morphology import SynapseConfig

ModelType = Literal["me-model", "synaptome"]
NexusMEModelType = "MEModel"
NexusSynaptomeType = "SingleNeuronSynaptome"


class UsedMEModel(BaseModel):
    model_self: str
    model_type: ModelType
    name: str


class SynaptomeModelResponse(BaseModel):
    self: str
    name: str
    description: Optional[str]
    model_type: ModelType
    created_by: str
    created_at: datetime

    me_model: UsedMEModel

    synapses: list[SynapseConfig]
