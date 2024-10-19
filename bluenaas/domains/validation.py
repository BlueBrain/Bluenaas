from pydantic import BaseModel


class PlaceSynapsesBodyRequest(BaseModel):
    formula: str


class PlaceSynapsesFormulaValidationResponse(BaseModel):
    valid: bool
    type: str | None = None
    message: str | None = None
