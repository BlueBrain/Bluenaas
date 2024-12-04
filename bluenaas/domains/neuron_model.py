from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

from bluenaas.domains.morphology import SynapseConfig
from bluenaas.domains.simulation import BrainRegion

ModelType = Literal["me-model", "synaptome", "m-model", "e-model"]
SupportedNexusNeuronModels = Literal[
    "https://neuroshapes.org/MEModel",
    "MEModel",
    "SingleNeuronSynaptome",
    "https://bbp.epfl.ch/ontologies/core/bmo/SingleNeuronSynaptome",
]

NexusMEModelType: SupportedNexusNeuronModels = "MEModel"
NexusMEModelExtendedType: SupportedNexusNeuronModels = "https://neuroshapes.org/MEModel"
NexusSynaptomeType: SupportedNexusNeuronModels = "SingleNeuronSynaptome"
NexusSynaptomeExtendedType: SupportedNexusNeuronModels = (
    "https://bbp.epfl.ch/ontologies/core/bmo/SingleNeuronSynaptome"
)

NexusMModelType = "NeuronMorphology"
NexusEModelType = "EModel"


class UsedModel(BaseModel):
    id: str
    type: ModelType
    name: str


class SynaptomeModelResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    type: ModelType
    created_by: str
    created_at: datetime

    brain_region: BrainRegion
    me_model: UsedModel

    synapses: list[SynapseConfig]


class MEModelResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    type: ModelType
    created_by: str
    created_at: datetime

    brain_region: BrainRegion
    m_model: UsedModel
    e_model: UsedModel
