#!/usr/bin/env bash

set -euo pipefail

enable debug
set -x

echo "configuring sqs"
LOCALSTACK_HOST=localhost
AWS_REGION=us-east-1

create_queue() {
    local CELERY_QUEUE=$1
    awslocal --endpoint-url=http://${LOCALSTACK_HOST}:4566 sqs create-queue --queue-name ${CELERY_QUEUE} --region ${AWS_REGION} --attributes VisibilityTimeout=30
}

create_queue "bluenaas"