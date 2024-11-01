from typing import Optional
from datetime import datetime
from urllib.parse import quote_plus

from bluenaas.external.nexus.nexus import Nexus
from bluenaas.domains.neuron_model import (
    NexusSynaptomeType,
    SynaptomeModelResponse,
    UsedMEModel,
)
from bluenaas.domains.morphology import SynapseConfig


def get_all_synaptome_models_for_project(
    token: str,
    org_id: str,
    project_id: str,
    offset: int,
    size: int,
    created_at_start: Optional[datetime],
    created_at_end: Optional[datetime],
) -> list[SynaptomeModelResponse]:
    nexus_helper = Nexus(
        {"token": token, "model_self_url": ""}
    )  # TODO: Remove model_id as a required field for nexus helper

    nexus_model_response = nexus_helper.fetch_resources_of_type(
        org_label=org_id,
        project_label=project_id,
        res_types=[NexusSynaptomeType],
        offset=offset,
        size=size,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )
    nexus_models = nexus_model_response["_results"]

    synaptome_models = []

    for nexus_model in nexus_models:
        verbose_model = nexus_helper.fetch_resource_by_self(nexus_model["_self"])
        file_url = verbose_model["distribution"]["contentUrl"]

        file_response = nexus_helper.fetch_file_by_url(file_url)
        distribution = file_response.json()

        synapses = distribution["synapses"]
        me_model_self = distribution["meModelSelf"]

        synaptome_models.append(
            SynaptomeModelResponse(
                self=nexus_model["_self"],
                name=nexus_model["name"],
                description=nexus_model.get("description"),
                model_type="synaptome",
                created_by=nexus_model["_createdBy"],
                created_at=nexus_model["_createdAt"],
                me_model=UsedMEModel(
                    model_self=me_model_self,
                    model_type="me-model",
                    name=verbose_model["used"]["name"],
                ),
                synapses=[
                    SynapseConfig.model_validate(synapse) for synapse in synapses
                ],
            )
        )
    return synaptome_models
