from loguru import logger
import sympy as sp
from http import HTTPStatus as status
from bluenaas.core.exceptions import BlueNaasError, BlueNaasErrorCode
from bluenaas.domains.validation import PlaceSynapsesFormulaValidationResponse  # type: ignore


def validate_synapse_generation_formula(
    formula: str,
):
    """
    Validates the given synapse generation formula by parsing it with sympy.

    Args:
        formula (str): The formula string to validate.

    Returns:
        dict: A dictionary containing the validation status, error type (if any),
              and a message describing the outcome.
              {
                  "valid": bool,        # True if formula is valid, False otherwise
                  "type": str or None,  # Error type if invalid, otherwise None
                  "message": str or None  # Error message or None if valid
              }

    Raises:
        BlueNaasError: If an unexpected exception occurs during validation.
    """
    try:
        expr = sp.sympify(formula)
        allowed_symbols = {sp.Symbol("x"), sp.Symbol("X")}
        symbols = expr.free_symbols

        if symbols.issubset(allowed_symbols):
            return PlaceSynapsesFormulaValidationResponse(
                valid=True,
            )
        else:
            # Handle case where symbols are invalid
            invalid_symbols = symbols - allowed_symbols
            return PlaceSynapsesFormulaValidationResponse(
                valid=False,
                type="InvalidSymbolsError",
                message=f"Invalid symbols found: {', '.join(str(s) for s in invalid_symbols)}",
            )
    except (sp.SympifyError, SyntaxError) as ex:
        logger.error(
            f"validating synapse generation formula failed [SympifyError, SyntaxError] {ex}"
        )
        return PlaceSynapsesFormulaValidationResponse(
            valid=False,
            type="SyntaxError",
            message=ex.__str__(),
        )
    except AttributeError as ex:
        logger.error(
            f"validating synapse generation formula failed [AttributeError] {ex}"
        )
        return PlaceSynapsesFormulaValidationResponse(
            valid=False,
            type="AttributeError",
            message=ex.__str__(),
        )
    except Exception as ex:
        logger.error(f"validating synapse generation formula failed {ex}")
        raise BlueNaasError(
            http_status_code=status.INTERNAL_SERVER_ERROR,
            error_code=BlueNaasErrorCode.INTERNAL_SERVER_ERROR,
            message="validating synapse generation formula failed",
            details=ex.__str__(),
        ) from ex
