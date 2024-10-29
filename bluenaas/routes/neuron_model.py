from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query


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
):
    pass


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
