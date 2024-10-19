from http import HTTPStatus
from typing import cast

from pydantic import Field
from bluenaas.domains.nexus import DeprecateNexusResponse
from bluenaas.external.nexus.nexus import Nexus
from urllib.parse import unquote
from loguru import logger
from bluenaas.core.exceptions import (
    BlueNaasError,
    BlueNaasErrorCode,
    ResourceDeprecationError,
)


def deprecate_simulation(
    token: str,
    org_id: str,
    project_id: str,
    simulation_uri: str = Field(..., description="URL-encoded simulation URI"),
) -> None:
    try:
        simulation_id = unquote(simulation_uri)
        nexus_helper = Nexus(
            {
                "token": token,
                "model_self_url": "",
            }
        )  # TODO: Remove model_id as a required field for nexus helper

        simulation_resource = nexus_helper.fetch_resource_for_org_project(
            org_label=org_id,
            project_label=project_id,
            resource_id=simulation_id,
        )
    except Exception as ex:
        logger.exception(f"Error while fetching simulation {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            message="Error while fetching simulation",
            details=ex.__str__(),
        ) from ex

    try:
        if not simulation_resource["_deprecated"]:
            res = nexus_helper.deprecate_resource(
                org_label=org_id,
                project_label=project_id,
                resource_id=simulation_id,
                previous_rev=simulation_resource["_rev"],
            )
            return DeprecateNexusResponse(
                id=res.get("@id"),
                deprecated=res.get("_deprecated"),
                updated_at=res.get("_updatedAt"),
            )

        return DeprecateNexusResponse(
            id=simulation_resource.get("@id"),
            deprecated=simulation_resource.get("_deprecated"),
            updated_at=simulation_resource.get("_updatedAt"),
        )
    except ResourceDeprecationError as ex:
        error = cast(dict, getattr(ex, "response_data", None))
        raise BlueNaasError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=BlueNaasErrorCode.NEXUS_ERROR,
            message=error.get("reason", "Error while deprecating simulation"),
            details=(
                error.get(
                    "@type",
                    "Nexus failed to deprecate the resource",
                )
            ),
        ) from ex
    except Exception as ex:
        logger.exception(f"Error while deprecating simulation {ex}")
        raise BlueNaasError(
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="Error while deprecating simulation",
            details=ex.__str__(),
        ) from ex
