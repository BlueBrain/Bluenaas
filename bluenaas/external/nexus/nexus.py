"""Nexus module."""

from datetime import datetime
import zipfile
import os
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlencode
from loguru import logger
import requests
from bluenaas.domains.simulation import (
    SingleNeuronSimulationConfig,
    StimulationItemResponse,
    SimulationStatus,
)
from bluenaas.domains.nexus import (
    NexusSimulationPayload,
    BaseNexusSimulationResource,
)
from bluenaas.config.settings import settings
from bluenaas.utils.ensure_list import ensure_list
from bluenaas.utils.generate_id import generate_id
from bluenaas.utils.util import get_model_path
from bluenaas.core.exceptions import ResourceDeprecationError, SimulationError
from typing import Any, Optional, Sequence
import json

HTTP_TIMEOUT = 10  # seconds

model_dir = Path("/opt/blue-naas/") / "models"
defaultIdBaseUrl = "https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model"

HOC_FORMAT = ["application/x-neuron-hoc", "application/hoc"]

RWX_TO_ALL = 0o777


def opener(path, flags):
    return os.open(path, flags, RWX_TO_ALL)


def extract_org_project_from_id(url) -> dict[str, str | None]:
    """Extracts the org and project of a resource id"""
    parts = url.split("/")
    if len(parts) >= 3:
        org_project = parts[-4:-2]
        return {"org": org_project[0], "project": org_project[1]}
    else:
        return {"org": None, "project": None}  # Handle URLs with fewer than 3 parts


def construct_time_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> str:
    """
    Constructs a time range string based on the given start and end dates.

    Args:
        start_date (Optional[datetime]): The start date of the range.
        end_date (Optional[datetime]): The end date of the range.

    Returns:
        str: The constructed time range string in the format 'start..end'.
    """
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ") if start_date else "*"
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ") if end_date else "*"

    return "{}..{}".format(start_str, end_str)


class Nexus:
    """Nexus class to help downloading the emodel files needed for simulation."""

    # pylint: disable=missing-function-docstring
    def __init__(self, params):
        self.headers = {}
        self.model_self_url = params["model_self_url"]
        base_and_id = self.model_self_url.split("/")
        self.model_id = unquote(base_and_id[-1])
        self.model_uuid = self.model_id.split("/")[-1]
        # join all except the last part (id)
        self.nexus_base = f'{"/".join(base_and_id[:-1])}/'
        self.headers.update({"Authorization": params["token"]})

    def fetch_resource_by_id(self, resource_id):
        org, project = extract_org_project_from_id(self.nexus_base).values()
        if org is None or project is None:
            raise Exception("org or project are missing")

        endpoint = f"{settings.NEXUS_ROOT_URI}/resolvers/{org}/{project}/_/{quote_plus(resource_id, safe=":")}"
        r = requests.get(endpoint, headers=self.headers, timeout=HTTP_TIMEOUT)
        if not r.ok:
            raise Exception("Error fetching resource", r.json())
        return r.json()

    def update_resource_by_id(
        self, org_label, project_label, resource_id, previous_rev, payload
    ):
        endpoint = f"{settings.NEXUS_ROOT_URI}/resources/{org_label}/{project_label}/_/{quote_plus(resource_id)}?rev={previous_rev}"
        payload_without_metadata = {
            k: v for k, v in payload.items() if not k.startswith("_")
        }

        r = requests.put(
            endpoint,
            headers=self.content_modification_headers(),
            data=json.dumps(payload_without_metadata),
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            raise Exception("Error updating resource", r.json())
        return r.json()

    def fetch_resource_by_self(self, resource_self):
        r = requests.get(resource_self, headers=self.headers, timeout=HTTP_TIMEOUT)
        if not r.ok:
            raise Exception("Error fetching resource", r.json())
        return r.json()

    def fetch_resource_for_org_project(self, org_label, project_label, resource_id):
        endpoint = f"{settings.NEXUS_ROOT_URI}/resolvers/{org_label}/{project_label}/_/{quote_plus(resource_id, safe=":")}"
        r = requests.get(
            endpoint,
            headers=self.headers,
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            raise Exception("Error fetching resource", r.json())
        return r.json()

    def deprecate_resource(self, org_label, project_label, resource_id, previous_rev):
        endpoint = f"{settings.NEXUS_ROOT_URI}/resources/{org_label}/{project_label}/_/{quote_plus(resource_id)}?rev={previous_rev}"
        r = requests.delete(
            endpoint,
            headers=self.content_modification_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            raise ResourceDeprecationError("Error deprecating resource", r.json())
        return r.json()

    def fetch_resources_of_type(
        self,
        org_label: str,
        project_label: str,
        res_types: Sequence[str],
        offset: int,
        size: int,
        created_at_start: datetime,
        created_at_end: datetime,
    ):
        query_params = [("type", res_type) for res_type in res_types]
        query_params.append(("size", str(size)))
        query_params.append(("from", str(offset)))
        query_params.append(
            ("createdAt", construct_time_range(created_at_start, created_at_end))
        )

        endpoint = f"{settings.NEXUS_ROOT_URI}/resources/{org_label}/{project_label}?{urlencode(query_params)}"
        r = requests.get(
            endpoint,
            headers=self.headers,
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            raise Exception("Error fetching resource", r.json())
        return r.json()

    def fetch_file_by_url(self, file_url):
        r = requests.get(file_url, headers=self.headers, timeout=HTTP_TIMEOUT)
        if not r.ok:
            raise Exception("Error fetching file", r.json())
        return r

    def fetch_file_metadata(self, file_url):
        r = requests.get(
            file_url,
            headers=self.headers | {"Accept": "application/ld+json"},
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            raise Exception("Error fetching file", r.json())
        return r

    def content_modification_headers(self):
        return self.headers | {
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    def save_file_to_nexus(
        self,
        payload: dict,
        content_type: str,
        filename: str,
        file_url: str,
        org_id: str,
        project_id: str,
    ) -> dict:
        stringified_data = json.dumps(payload)

        # Prepare the files for the POST request
        files = {"file": (filename, stringified_data, content_type)}
        file_headers = self.headers | {
            # mandatory to upload to a S3 storage (AWS)
            "x-nxs-file-content-length": str(len(stringified_data))
        }

        response = requests.post(
            file_url, headers=file_headers, files=files, timeout=HTTP_TIMEOUT
        )

        if not response.ok:
            raise Exception("Error saving file to nexus", response.json())
        return response.json()

    def create_nexus_distribution(
        self, payload: dict, filename: str, org_id: str, project_id: str
    ):
        content_type = "application/json"
        file_url = f"{settings.NEXUS_ROOT_URI}/files/{org_id}/{project_id}"

        saved_file = self.save_file_to_nexus(
            payload=payload,
            content_type=content_type,
            filename=filename,
            file_url=file_url,
            org_id=org_id,
            project_id=project_id,
        )

        distribution_url = f"{settings.NEXUS_ROOT_URI}/files/{org_id}/{project_id}/{quote_plus(saved_file["@id"])}?rev={saved_file["_rev"]}"
        distribution = {
            "@type": "DataDownload",
            "name": saved_file["_filename"],
            "contentSize": {
                "unitCode": "bytes",
                "value": saved_file["_bytes"],
            },
            "contentUrl": distribution_url,
            "encodingFormat": saved_file["_mediaType"],
            "digest": {
                "algorithm": saved_file["_digest"]["_algorithm"],
                "value": saved_file["_digest"]["_value"],
            },
        }
        return distribution

    # Note: This function doesn't seem to work for distributions uploaded on s3. See discussion here - https://bluebrainproject.slack.com/archives/G013PKBUHT2/p1728567806810799
    def update_nexus_distribution(
        self, file_url: str, filename: str, content_type: str, data_to_add: dict
    ):
        current_distribution = self.fetch_file_by_url(file_url=file_url).json()

        updated_json = current_distribution | data_to_add

        # Prepare the files for the PUT request
        files = {"file": (filename, json.dumps(updated_json), content_type)}
        file_headers = self.headers | {
            # mandatory to upload to a S3 storage (AWS)
            "x-nxs-file-content-length": str(len(updated_json))
        }

        response = requests.put(
            file_url,
            headers=file_headers,
            files=files,
            timeout=HTTP_TIMEOUT,
        )

        if not response.ok:
            raise Exception(
                f"Error updating distribution: {response.status_code}", response.json()
            )
        return response.json()

    def compose_url(self, url):
        return self.nexus_base + quote_plus(url, safe=":")

    def get_workflow_id(self, emodel_resource):
        return emodel_resource["generation"]["activity"]["followedWorkflow"]["@id"]

    def get_configuration_id(self, emodel_resource):
        workflow_id = self.get_workflow_id(emodel_resource)
        workflow_resource = self.fetch_resource_by_id(workflow_id)

        configuration = None
        workflow_resource_list = ensure_list(workflow_resource["hasPart"], dict)
        for part in workflow_resource_list:
            if part["@type"] == "EModelConfiguration":
                configuration = part
                break

        if configuration is None:
            raise Exception("No E-Model configuration found")

        return configuration["@id"]

    def get_emodel_configuration(self, emodel_resource):
        configuration_id = self.get_configuration_id(emodel_resource)
        return self.fetch_resource_by_id(configuration_id)

    def get_morphology(self, morph_id):
        morphology_resource = self.fetch_resource_by_id(morph_id)

        swc = None
        distributions = ensure_list(morphology_resource["distribution"], dict)
        for distribution in distributions:
            if distribution["encodingFormat"] == "application/swc":
                swc = distribution
                break

        if swc is None:
            raise Exception("SWC format not found in NeuronMorphology distribution")

        file = self.fetch_file_by_url(swc["contentUrl"])

        return {"name": swc["name"], "content": file.text}

    def get_emodel_morphology(self, configuration):
        morphology = None
        for item in configuration["uses"]:
            if item["@type"] == "NeuronMorphology":
                morphology = item
                break
        if morphology is None:
            raise Exception("NeuronMorphology not found")

        return self.get_morphology(morphology["@id"])

    def get_memodel_morphology(self, memodel_resource):
        morphology_id = None
        for haspart in ensure_list(memodel_resource["hasPart"], dict):
            if haspart.get("@type") == "NeuronMorphology":
                morphology_id = haspart.get("@id")
        if morphology_id is None:
            raise Exception("No Morphology found in ME-Model")

        return self.get_morphology(morphology_id)

    def get_mechanisms(self, configuration):
        # fetch only SubCellularModelScripts. Morphologies will be fetched later
        scripts = []
        for config in ensure_list(configuration["uses"], dict):
            if config.get("@type") != "NeuronMorphology":
                scripts.append(config)

        model_resources = []
        for script in scripts:
            script_resource = self.fetch_resource_by_id(script["@id"])
            model_resources.append(script_resource)

        # TODO: Add these configuration to the model
        extra_mechanisms = [
            "https://openbluebrain.com/api/nexus/v1/resources/bbp/mmb-point-neuron-framework-model/_/https:%2F%2Fbbp.epfl.ch%2Fneurosciencegraph%2Fdata%2Fsynapticphysiologymodels%2Fe3c32384-5cb1-4dd3-a8c9-f6c23bea6b27",
            "https://openbluebrain.com/api/nexus/v1/resources/bbp/mmb-point-neuron-framework-model/_/https:%2F%2Fbbp.epfl.ch%2Fneurosciencegraph%2Fdata%2Fsynapticphysiologymodels%2F3965bc40-ca30-475b-98be-cfa3e22057b5",
        ]
        for extra_mech in extra_mechanisms:
            mech = self.fetch_resource_by_self(extra_mech)
            model_resources.append(mech)
        # logger.info(f'@@-> {model_resources=}')
        mechanisms = []
        for model_resource in model_resources:
            distributions = ensure_list(model_resource["distribution"], dict)
            logger.info(f'@@-> ds:{model_resource["distribution"]}')
            distribution = list(
                filter(
                    lambda x: x.get("encodingFormat") == "application/mod"
                    or x.get("encodingFormat") == "application/neuron-mod",
                    distributions,
                )
            )[0]

            file = self.fetch_file_by_url(distribution["contentUrl"])
            mechanisms.append({"name": distribution["name"], "content": file.text})

        return mechanisms

    def get_script_resource(self, emodel_resource):
        workflow_id = self.get_workflow_id(emodel_resource)
        workflow_resource = self.fetch_resource_by_id(workflow_id)

        script = None
        for generated in ensure_list(workflow_resource["generates"], dict):
            if generated["@type"] == "EModelScript":
                script = generated
                break

        if script is None:
            raise Exception("No E-Model script found")

        return self.fetch_resource_by_id(script["@id"])

    def get_hoc_file(self, emodel_resource):
        emodel_script = self.get_script_resource(emodel_resource)
        distribution = emodel_script["distribution"]

        for dist in emodel_script["distribution"]:
            if dist["encodingFormat"] in HOC_FORMAT:
                distribution = dist
                break

        emodel_script_url = distribution["contentUrl"]

        r = self.fetch_file_by_url(emodel_script_url)
        return r.text

    def create_compressed_file(self, hoc_file, morphology_obj, mechanisms):
        final_compressed_file = model_dir / f"{self.model_uuid}.tar"

        with zipfile.ZipFile(final_compressed_file, mode="w") as archive:
            archive.writestr("cell.hoc", hoc_file)

            morph_name = morphology_obj["name"]
            archive.writestr(
                f"morphology/{morph_name}",
                morphology_obj["content"],
            )

            for mechanism in mechanisms:
                mech_name = mechanism["name"]
                archive.writestr(
                    f"mechanisms/{mech_name}",
                    mechanism["content"],
                )

    def create_file(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", opener=opener) as f:
            f.write(content)

    def copy_file_content(self, source_file: Path, target_file: Path):
        with open(source_file, "r") as src, open(
            target_file, "w", opener=opener
        ) as dst:
            dst.write(src.read())

    def create_model_folder(self, hoc_file, morphology_obj, mechanisms):
        output_dir = get_model_path(self.model_uuid)

        self.create_file(output_dir / "cell.hoc", hoc_file)

        morph_name = morphology_obj["name"]
        self.create_file(
            output_dir / "morphology" / morph_name, morphology_obj["content"]
        )

        for mechanism in mechanisms:
            mech_name = mechanism["name"]
            self.create_file(
                output_dir / "mechanisms" / mech_name, mechanism["content"]
            )

        self.copy_file_content(
            Path("/app/bluenaas/config/VecStim.mod"),
            output_dir / "mechanisms" / "VecStim.mod",
        )

    def get_emodel_resource(self, resource):
        if "MEModel" in resource["@type"]:
            logger.debug("Model is ME-Model")
            emodel_id = None
            if "hasPart" not in resource:
                raise AttributeError("ME-Model resource has no 'hasPart' metadata")
            for haspart in resource["hasPart"]:
                if haspart["@type"] == "EModel":
                    emodel_id = haspart["@id"]
            if emodel_id is None:
                raise Exception("No E-Model found in ME-Model")
            emodel_resource = self.fetch_resource_by_id(emodel_id)
        else:
            logger.debug("Model is E-Model")
            emodel_resource = resource
        return emodel_resource

    def download_model(self):
        resource = self.fetch_resource_by_id(self.model_id)
        # could be E-Model or ME-Model
        emodel_resource = self.get_emodel_resource(resource)
        logger.debug("E-Model resource fetched")
        configuration = self.get_emodel_configuration(emodel_resource)
        logger.debug("E-Model configuration fetched")
        mechanisms = self.get_mechanisms(configuration)
        logger.debug("E-Model mechanisms fetched")
        hoc_file = self.get_hoc_file(emodel_resource)
        logger.debug("E-Model hoc file fetched")
        if "MEModel" in resource["@type"]:
            logger.debug("Fetching Morphology from ME-Model")
            morphology_obj = self.get_memodel_morphology(resource)
        else:
            logger.debug("Fetching Morphology from E-Model")
            morphology_obj = self.get_emodel_morphology(configuration)
        logger.debug("Morphology fetched")
        self.create_model_folder(hoc_file, morphology_obj, mechanisms)
        logger.debug("E-Model folder created")

    def get_currents(self):
        resource = self.fetch_resource_by_id(self.model_id)
        # TODO: this should be the right way to do it when analysis is ready
        # With the changes to ME-model shape
        # if (
        #     "MEModel" in resource["@type"]
        #     and resource["validated"] is True
        #     and "parameter" in resource
        # ):
        #     logger.debug("Getting currents from ME-Model")
        #     param_dict = {
        #         param["name"]: param["value"] for param in resource["parameter"]
        #     }
        #     holding_current = param_dict.get("holding_current")
        #     threshold_current = param_dict.get("threshold_current")
        #     logger.debug(
        #         f"currents are: holding: {holding_current}, threshold: {threshold_current}"
        #     )
        #     return [holding_current, threshold_current]

        if "MEModel" in resource["@type"] and resource["validated"]:
            return [resource["holding_current"], resource["threshold_current"]]

        logger.debug("Getting currents from E-Model")
        emodel_resource = self.get_emodel_resource(resource)
        emodel_script = self.get_script_resource(emodel_resource)

        return [
            0
            if "holding_current" not in emodel_script
            else emodel_script["holding_current"],
            0
            if "threshold_current" not in emodel_script
            else emodel_script["threshold_current"],
        ]

    def get_model_uuid(self):
        return self.model_uuid

    def create_simulation_resource(
        self,
        simulation_config: SingleNeuronSimulationConfig,
        status: SimulationStatus,
        org_id: str,
        project_id: str,
    ) -> dict:
        # Step 1: Get me_model
        try:
            model = self.fetch_resource_by_id(self.model_id)
        except Exception:
            raise SimulationError(f"No me_model with self {self.model_id} found")

        # Step 2: Create simulation resource with status = "PENDING"
        try:
            sim_name = (
                "single-neuron-simulation-{}".format(generate_id(10))
                if simulation_config.type == "single-neuron-simulation"
                else "synaptome-simulation-{}".format(generate_id(10))
            )
            description = "simulation"
            simulation_resource = self.prepare_nexus_simulation(
                sim_name=sim_name,
                description=description,
                config=simulation_config,
                model=model,
                status=status,
            )
            simulation_resource_url = f"{settings.NEXUS_ROOT_URI}/resources/{org_id}/{project_id}?indexing=sync"
            simulation_response = requests.post(
                url=simulation_resource_url,
                headers=self.content_modification_headers(),
                data=simulation_resource.model_dump_json(by_alias=True),
                timeout=HTTP_TIMEOUT,
            )
            simulation_response.raise_for_status()
            return simulation_response.json()
        except Exception as error:
            raise SimulationError(
                f"Failed to create simulation resource {error} {simulation_response.json()}"
            )

    def update_simulation_status(
        self,
        org_id: str,
        project_id: str,
        resource_self: str,
        status: SimulationStatus,
        is_draft: bool,
        err: Optional[str] = None,
    ):
        try:
            simulation_resource = self.fetch_resource_by_self(resource_self)

            updated_resource = simulation_resource | {
                "status": status,
                "isDraft": is_draft,
                **({"error": err} if err is not None else {}),
            }

            return self.update_resource_by_id(
                org_label=org_id,
                project_label=project_id,
                resource_id=simulation_resource["@id"],
                previous_rev=simulation_resource["_rev"],
                payload=updated_resource,
            )
        except Exception as e:
            logger.exception(
                f"Could not update simulation resource {resource_self} with status {status}. Exception {e}"
            )
            raise SimulationError(
                f"Could not update simulation resource {resource_self} with status {status}"
            )

    def save_simulation_results(
        self,
        resource_self: str,
        config: dict,
        stimulus_plot_data: list[StimulationItemResponse],
        org_id: str,
        project_id: str,
        status: SimulationStatus,
        is_draft: bool,
        results: Any,
    ):
        # Step 1: Create a distribution file to save results.
        try:
            simulation_config = SingleNeuronSimulationConfig.model_validate(config)
            distribution_payload = NexusSimulationPayload(
                config=simulation_config,
                simulation=results,
                stimulus=stimulus_plot_data,
            )
            distribution_name = (
                "simulation-config-single-neuron.json"
                if simulation_config.type == "single-neuron-simulation"
                else "simulation-config-synaptome.json"
            )
            distribution_resource = self.create_nexus_distribution(
                payload=distribution_payload.model_dump(by_alias=True),
                filename=distribution_name,
                org_id=org_id,
                project_id=project_id,
            )
        except Exception as e:
            logger.exception(
                f"Could not create distribution with simulation results for resource {resource_self}. Exception {e}"
            )
            raise SimulationError(
                f"Could not create distribution with simulation results for resource {resource_self}"
            )

        # Step 2: Add distribution file to simulation resource as well as update status
        try:
            simulation_resource = self.fetch_resource_by_self(resource_self)

            updated_resource = simulation_resource | {
                "status": status,
                "isDraft": is_draft,
                "distribution": [distribution_resource],
            }

            return self.update_resource_by_id(
                org_label=org_id,
                project_label=project_id,
                resource_id=simulation_resource["@id"],
                previous_rev=simulation_resource["_rev"],
                payload=updated_resource,
            )
        except Exception as e:
            logger.exception(
                f"Could not update simulation resource {resource_self} with status {status}. Exception {e}"
            )
            raise SimulationError(
                f"Could not update simulation resource {resource_self} with status {status}"
            )

    def prepare_nexus_simulation(
        self,
        sim_name: str,
        description: str,
        config: SingleNeuronSimulationConfig,
        model: dict,
        status: str,
    ):
        record_locations = [
            f"{r.section}_{r.offset}" for r in ensure_list(config.record_from, str)
        ]
        return BaseNexusSimulationResource(
            type=["Entity", "SingleNeuronSimulation"]
            if config.type == "single-neuron-simulation"
            else ["Entity", "SynaptomeSimulation"],
            name=sim_name,
            description=description,
            context="https://bbp.neuroshapes.org",
            distribution=[],
            injectionLocation=config.current_injection.inject_to,
            recordingLocation=ensure_list(record_locations, str),
            brainLocation=model["brainLocation"],
            # Model can be MEModel or SingleNeuronSynaptome
            used={"@type": model["@type"], "@id": model["@id"]},
            isDraft=True,
            status=status,
        )

    def create_simulation_distribution(
        self,
        config: SingleNeuronSimulationConfig,
        stimulus: list[StimulationItemResponse],
        org_id: str,
        project_id: str,
    ):
        distribution_payload = NexusSimulationPayload(
            config=config, simulation=None, stimulus=stimulus
        )
        distribution_name = (
            "simulation-config-single-neuron.json"
            if config.type == "single-neuron-simulation"
            else "simulation-config-synaptome.json"
        )
        distribution_resource = self.create_nexus_distribution(
            payload=distribution_payload.model_dump(by_alias=True),
            filename=distribution_name,
            org_id=org_id,
            project_id=project_id,
        )
        return distribution_resource
