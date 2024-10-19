FROM python:3.12 as builder

RUN pip install poetry==1.4.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/blue-naas-cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN apt-get update \
  && apt-get install -q -y --no-install-recommends build-essential libhdf5-dev \
  && pip install --no-cache-dir --upgrade setuptools pip wheel \
  && pip install --no-cache-dir neuron==8.2.4

RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --no-root --no-dev --no-interaction

RUN mkdir -p /opt/blue-naas/models

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY ./bluenaas /app/bluenaas
COPY ./scripts/celery.sh /app/celery.sh

RUN chmod +x /app/celery.sh

EXPOSE 8000

CMD ["./scripts/entrypoint.sh"]
