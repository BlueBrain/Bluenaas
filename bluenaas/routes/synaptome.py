"""
Synapse Placement Generation:
Exposes an endpoint (`/generate-placement`) to generate synapse placements based on user-provided parameters
"""

from fastapi import APIRouter, Depends, Query, Request
from bluenaas.domains.morphology import (
    SynapsePlacementBody,
    SynapsePlacementResponse,
)
from bluenaas.infrastructure.kc.auth import verify_jwt
from bluenaas.services.synapses_placement import generate_synapses_placement

router = APIRouter(
    prefix="/synaptome",
    tags=["Synaptome"],
)


@router.post(
    "/generate-placement",
    response_model=SynapsePlacementResponse,
    summary="Get synapses coordinates in 3D plan",
)
def place_synapses(
    request: Request,
    params: SynapsePlacementBody,
    model_self: str = Query(),
    token: str = Depends(verify_jwt),
) -> SynapsePlacementResponse:
    """
    Generates synapse position coordinates for a 3D plan based on the provided parameters.

    This endpoint accepts a set of parameters to calculate the positions of synapses
    in a 3D model.
    """
    return generate_synapses_placement(
        model_self=model_self,
        token=token,
        params=params,
        req_id=request.state.request_id,
    )
