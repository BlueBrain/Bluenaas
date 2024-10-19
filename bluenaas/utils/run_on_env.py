from typing import Callable, Dict, Optional, TypeVar

from bluenaas.config.settings import ENVS, settings

T = TypeVar("T")


def run_on_env(
    env_fns: Dict[ENVS, Callable[..., T]],
    fallback: Optional[T] = None,
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Executes a function based on the current deployment environment or returns a fallback value.

    Args:
        env_fns (Dict[ENVS, Callable[..., R]]):
            A dictionary mapping environment names (e.g., "production", "development") to callables (functions).
        fallback (Optional[R]):
            A fallback value to return if no function is found for the current environment.
        *args:
            Positional arguments to pass to the function.
        **kwargs:
            Keyword arguments to pass to the function.

    Returns:
        Optional[R]:
            - The result of the function corresponding to the current environment.
            - The `fallback` value if no function is found for the current environment.
            - `None` if neither a function nor a fallback is available.

    Example:
        >>> def prod_fn():
        ...     return "Production function"

        >>> def dev_fn():
        ...     return "Development function"

        >>> env_functions = {
        ...     "production": prod_fn,
        ...     "development": dev_fn
        ... }

        >>> settings.DEPLOYMENT_ENV = "production"
        >>> result = run_on_env(env_functions, fallback="Default")
        "Production function"
    """
    current_env = settings.DEPLOYMENT_ENV
    fn = env_fns.get(current_env)

    if fn:
        return fn(*args, **kwargs)
    elif fallback:
        return fallback
    else:
        return None
