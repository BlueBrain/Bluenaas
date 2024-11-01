import json
from pathlib import Path
import pandas as pd

from bluenaas.domains.morphology import SynapseSeries
from bluenaas.domains.simulation import (
    CurrentInjectionConfig,
    SynaptomeSimulationConfig,
)


def serialize_template_params(params: any) -> str:
    # Convert Path to string and pydantic dataclass to dict
    data = {
        "template_filepath": str(params.template_filepath),
        "morph_filepath": str(params.morph_filepath),
        "template_format": params.template_format,
        "emodel_properties": params.emodel_properties.__dict__
        if params.emodel_properties
        else None,
    }
    return json.dumps(data)


# Deserialize JSON string back to TemplateParams
def deserialize_template_params(json_str: str):
    from bluecellulab.cell.template import TemplateParams, EmodelProperties

    data = json.loads(json_str)

    # Convert string back to Path and rebuild EmodelProperties dataclass
    template_filepath = Path(data["template_filepath"])
    morph_filepath = Path(data["morph_filepath"])

    emodel_properties_data = data["emodel_properties"]
    emodel_properties = None
    if emodel_properties_data:
        emodel_properties = EmodelProperties(
            threshold_current=emodel_properties_data["threshold_current"],
            holding_current=emodel_properties_data["holding_current"],
            AIS_scaler=emodel_properties_data.get("AIS_scaler", 1.0),
            soma_scaler=emodel_properties_data.get("soma_scaler", 1.0),
        )

    return TemplateParams(
        template_filepath=template_filepath,
        morph_filepath=morph_filepath,
        template_format=data["template_format"],
        emodel_properties=emodel_properties,
    )


def serialize_synapse_series(synapse: SynapseSeries) -> dict:
    return {
        "id": synapse["id"],
        "series": synapse["series"].to_dict(),
        "directCurrentConfig": synapse["directCurrentConfig"].model_dump(),
        "synapseSimulationConfig": synapse["synapseSimulationConfig"].model_dump(),
        "frequencies_to_apply": synapse["frequencies_to_apply"],
    }


def serialize_synapse_series_list(synapse_series_list: list[SynapseSeries]) -> str:
    return json.dumps(
        [serialize_synapse_series(synapse) for synapse in synapse_series_list]
    )


def serialize_synapse_series_dict(
    synapse_series_dict: dict[float, list[SynapseSeries]],
) -> str:
    return json.dumps(
        {
            k: [serialize_synapse_series(synapse) for synapse in v]
            for k, v in synapse_series_dict.items()
        }
    )


def deserialize_synapse_series(data: dict) -> SynapseSeries:
    return {
        "id": data["id"],
        "series": pd.Series(data["series"]),  # Convert dict back to pandas.Series
        "directCurrentConfig": CurrentInjectionConfig(**data["directCurrentConfig"]),
        "synapseSimulationConfig": SynaptomeSimulationConfig(
            **data["synapseSimulationConfig"]
        ),
        "frequencies_to_apply": data["frequencies_to_apply"],
    }


def deserialize_synapse_series_list(serialized_data: str) -> list[SynapseSeries]:
    return [deserialize_synapse_series(item) for item in json.loads(serialized_data)]


def deserialize_synapse_series_dict(
    serialized_data: str,
) -> dict[float, list[SynapseSeries]]:
    data = json.loads(serialized_data)
    return {
        float(k): [deserialize_synapse_series(item) for item in v]
        for k, v in data.items()
    }
