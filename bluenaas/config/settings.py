from os import getenv
from typing import Literal, TypeGuard, get_args

from dotenv import load_dotenv
from pydantic_core import Url
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv("")

ENVS = Literal["development", "testing", "staging", "production"]


def _is_valid_env(env: str | None) -> TypeGuard[ENVS]:
    return env in get_args(ENVS)


_ENV = getenv("DEPLOYMENT_ENV")
_DEPLOYMENT_ENV = _ENV if _is_valid_env(_ENV) else "development"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # `.env.local` takes priority over `.env`
        env_file=(".env", f".env.{_DEPLOYMENT_ENV}", ".env.local"),
        extra="allow",
    )

    APP_NAME: str = "BlueNaas Service"
    APP_DEBUG: bool = False
    DEPLOYMENT_ENV: ENVS = _DEPLOYMENT_ENV
    BASE_PATH: str = ""
    CORS_ORIGINS: list[str] = []
    NEXUS_ROOT_URI: Url = Url("https://openbluebrain.com/api/nexus/v1")

    KC_SERVER_URI: str = "http://localhost:9090/"
    KC_CLIENT_ID: str = "obpapp"
    KC_CLIENT_SECRET: str = "obp-secret"
    KC_REALM_NAME: str = "obp-realm"

    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0
    SENTRY_PROFILES_SAMPLE_RATE: float = 1.0

    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"
    CELERY_APP_NAME: str = "bluenaas"
    CELERY_QUE_SIMULATIONS: str = "simulations"

    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    AWS_REGION: str = "eu-north-1"
    AWS_CLUSTER_NAME: str = "bnaas-cluster-01"
    AWS_SERVICE_NAME: str = "bnaas-service"

    AWS_TASK_PROTECTION_EXPIRE_IN_MIN: int = 60
    AWS_MAX_ECS_TASKS: int = 8


settings = Settings()
