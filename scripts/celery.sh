#! /bin/sh

ENV=${ENV:-development}  # Default is 'development' if ENV is not set
CELERY_APP="bluenaas.infrastructure.celery"

echo ${WORKER_NAME}
echo ${QUEUE_NAME}
echo ${POOL_TYPE}

# Add QUEUE_NAME option only if QUEUE_NAME is set
if [ -n "${QUEUE_NAME}" ]; then
    QUEUE_OPTION="-Q ${QUEUE_NAME}"
else
    QUEUE_OPTION=""
fi

if [ -n "${POOL_TYPE}" ]; then
    POOL_OPTION="-P ${POOL_TYPE}"
else
    POOL_OPTION=""
fi

if [ "$ENV" = "production" ]; then
    CMD="celery -A ${CELERY_APP} worker -n ${WORKER_NAME}@%h  -l WARNING  -E"
    echo "Running Celery Worker '${WORKER_NAME}' in production mode"
    exec $CMD
else
    echo "Running Celery Worker '${WORKER_NAME}' in development mode with auto-restart"
    watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- \
        celery -A ${CELERY_APP} worker -n ${WORKER_NAME}@%h ${QUEUE_OPTION} ${POOL_OPTION} -l WARNING -E
fi