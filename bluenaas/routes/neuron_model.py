from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, Depends

from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.services.synaptome.get_all_synaptome_models_for_project import (
    get_all_synaptome_models_for_project,
)

router = APIRouter(
    prefix="/neuron-model",
    tags=["Neuron Models"],
)


@router.get(
    "/{org_id}/{project_id}/me-models",
    summary="Retrieve all me models for a specific project",
)
def retrieve_me_models(
    org_id: str,
    project_id: str,
    page_offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
):
    pass


@router.get(
    "/{org_id}/{project_id}/me-models/{model_id}",
    summary="Retrieve specific model in a project",
)
def retrieve_me_model(
    model_id: str,
    org_id: str,
    project_id: str,
    page_offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
):
    pass


@router.get(
    "/{org_id}/{project_id}/synaptome-models",
    summary="Retrieve all synaptome models for a specific project",
)
def retrieve_synaptome_models(
    org_id: str,
    project_id: str,
    page_offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    token: str = Depends(verify_jwt),
):
    return get_all_synaptome_models_for_project(
        token=token,
        org_id=org_id,
        project_id=project_id,
        offset=page_offset,
        size=page_size,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )


@router.get(
    "/{org_id}/{project_id}/synaptome-models/{model_id}",
    summary="Retrieve single synaptome model in a specific project",
)
def retrieve_synaptome_model(
    model_id: str,
    org_id: str,
    project_id: str,
    page_offset: int = 0,
    page_size: int = 20,
    created_at_start: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    created_at_end: Optional[datetime] = Query(
        None, description="Filter by createdAt date (YYYY-MM-DDTHH:MM:SSZ)"
    ),
):
    pass
