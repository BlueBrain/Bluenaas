from typing import List, TypeVar, Union

T = TypeVar("T")


def ensure_list(payload: Union[List[T], T], expected_type: T) -> List[T]:
    # If the payload is a single item, wrap it in a list
    if not isinstance(payload, list):
        payload = [payload]

    elif isinstance(payload, list):
        return payload
    else:
        raise ValueError(
            f"All elements in the payload must be of type {expected_type.__name__}."
        )
