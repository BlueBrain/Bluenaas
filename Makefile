SHELL := /bin/bash

SERVICE_NAME=bluenaas-single-cell-svc

define HELPTEXT
	Usage: make COMMAND
	commands for managing the project
	
	Commands:
		dev		Run development api server.
		start	Run app in a container (use this one)
		dockerbuild-os	Build docker image mac
		dockerbuild-linux	Build docker image linux

endef
export HELPTEXT

help:
	@echo "$$HELPTEXT"

dev:
	poetry run uvicorn bluenaas.app:app --reload --port 8081

start:
	docker compose -f docker-compose.yml up

dockerbuild-linux:
	docker build . -t ${SERVICE_NAME} --platform=linux/amd64

dockerbuild-os:
	docker build . -t ${SERVICE_NAME}

format:	
	poetry run ruff format

format-check:
	poetry run ruff format --check

lint:
	poetry run ruff check --fix

lint-check:
	poetry run ruff check
	
type-check:
	poetry run mypy . --strict