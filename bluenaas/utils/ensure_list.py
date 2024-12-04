from typing import List, TypeVar, Union, overload

T = TypeVar("T")


@overload
def ensure_list(arg: List[T]) -> List[T]: ...
@overload
def ensure_list(arg: T) -> List[T]: ...
def ensure_list(arg: Union[T, List[T]]) -> List[T]:
    if isinstance(arg, list):
        return arg
    return [arg]
