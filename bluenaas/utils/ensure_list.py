from typing import List, TypeVar, Union

T = TypeVar("T")


def ensure_list(payload: Union[List[T], T], expected_type: T) -> List[T]:
    # If the payload is a single item, wrap it in a list
    if not isinstance(payload, list):
        return [payload]

    elif isinstance(payload, list):
        return payload
