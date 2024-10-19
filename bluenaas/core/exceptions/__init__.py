from enum import StrEnum
from http import HTTPStatus

from pydantic import BaseModel


class BlueNaasErrorCode(StrEnum):
    """
    Error codes of the blue naas service
    """

    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    UNKNOWN_BLUENAAS_ERROR = "UNKNOWN_BLUENAAS_ERROR"
    SYNAPSE_PLACEMENT_ERROR = "SYNAPSE_PLACEMENT_ERROR"
    SIMULATION_ERROR = "SIMULATION_ERROR"
    MORPHOLOGY_GENERATION_ERROR = "MORPHOLOGY_GENERATION_ERROR"
    DATABASE_URI_NOT_SET = "DATABASE_URI_NOT_SET"
    NEXUS_ERROR = "NEXUS_ERROR"


class BlueNaasError(Exception):
    """Base class for blue naas service exceptions."""

    message: str
    error_code: str | None
    http_status_code: HTTPStatus
    details: str | None

    def __init__(
        self,
        *,
        message: str,
        error_code: BlueNaasErrorCode | None,
        details: str | None = None,
        http_status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ):
        super().__init__(message, error_code, http_status_code)
        self.message = message
        self.error_code = error_code
        self.http_status_code = http_status_code
        self.details = details

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f'{class_name}(message="{self.message}", error_code={self.error_code}, details={self.details}, http_status_code={self.http_status_code})'


class BlueNaasErrorResponse(BaseModel):
    """The format of an error response"""

    error_code: BlueNaasErrorCode | None
    message: str | None = None
    details: str | None = None


class SimulationError(Exception):
    def __init__(self, message: str = "Simulation failed") -> None:
        self.message = message
        self.exc_type = type(self).__name__
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.exc_type}] {self.message}"

    def __reduce__(self):
        return (self.__class__, (self.message,))


class ChildSimulationError(Exception):
    def __init__(self, message: str = "Child simulation failed") -> None:
        self.message = message
        self.exc_type = type(self).__name__
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return f"[{self.exc_type}] {self.message}"


class SynapseGenerationError(Exception):
    def __init__(self, message: str = "Synapse generation failed") -> None:
        self.message = message
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class MorphologyGenerationError(Exception):
    def __init__(self, message: str = "Morphology generation failed") -> None:
        self.message = message
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class StimulationPlotGenerationError(Exception):
    def __init__(self, message: str = "Stimulation plot generation failed") -> None:
        self.message = message
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class ResourceDeprecationError(Exception):
    def __init__(self, message, response_data):
        super().__init__(message)
        self.response_data = response_data
