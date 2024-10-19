from fastapi import APIRouter, Depends, Query, Request

from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.services.morphology import get_single_morphology
from bluenaas.services.morphology_dendrogram import get_single_morphology_dendrogram

router = APIRouter(
    prefix="/morphology",
    tags=["Morphology"],
)


@router.get(
    "",
    summary="Morphology data",
)
def retrieve_morphology(
    request: Request,
    model_self: str = Query(""),
    token: str = Depends(verify_jwt),
):
    """
    Retrieves morphology data for a specified model.
    """
    return get_single_morphology(
        model_self=model_self,
        token=token,
        req_id=request.state.request_id,
    )


@router.get(
    "/dendrogram",
    summary="Dendrogram morphology data",
)
def retrieve_morphology_dendrogram(
    request: Request,
    model_self: str = Query(""),
    token: str = Depends(verify_jwt),
):
    """
    Retrieves dendrogram morphology data for a specified model.
    """
    return get_single_morphology_dendrogram(
        model_self=model_self,
        token=token,
        req_id=request.state.request_id,
    )
