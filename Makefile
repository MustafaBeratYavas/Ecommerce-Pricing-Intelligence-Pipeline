.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
	VENV_BIN := .venv/Scripts
	VENV_PYTHON := .venv/Scripts/python.exe
	DOCKER_COMPOSE_DEFAULT := docker-compose
	PATH_SEPARATOR := ;
else
	VENV_BIN := .venv/bin
	VENV_PYTHON := .venv/bin/python
	DOCKER_COMPOSE_DEFAULT := docker compose
	PATH_SEPARATOR := :
endif

PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python)
DOCKER ?= docker
DOCKER_COMPOSE ?= $(DOCKER_COMPOSE_DEFAULT)
COMPOSE_SERVICE ?= ecommerce-pricing-intelligence-pipeline
IMAGE_NAME ?= ecommerce-pricing-intelligence-pipeline:latest
PROD_IMAGE_NAME ?= ecommerce-pricing-intelligence-pipeline:prod
SEED_FILE ?= product_codes.txt
COVERAGE_MIN ?= 80
export PRE_COMMIT_HOME ?= .pre-commit-cache
ifneq ($(wildcard $(VENV_BIN)),)
export PATH := $(VENV_BIN)$(PATH_SEPARATOR)$(PATH)
endif

SRC_DIRS := src tests
UNIT_TESTS := tests/unit

.PHONY: help install install-dev lint format format-check fix type-check test test-cov pip-check pre-commit pre-commit-install validate ci profile seed run analysis docker-config docker-build docker-prod-build docker-run docker-profile docker-scrape docker-analysis docker-seed docker-test docker-shell

help:
	@echo Available targets:
	@echo   install             Install runtime dependencies
	@echo   install-dev         Install runtime and development dependencies
	@echo   profile             Create or refresh the local browser profile
	@echo   seed                Seed local product targets from SEED_FILE
	@echo   run                 Run the local scraping pipeline
	@echo   analysis            Run the local strategic analytics engine
	@echo   docker-config       Validate the Compose configuration
	@echo   docker-build        Build the Docker image
	@echo   docker-prod-build   Build the production Docker image
	@echo   docker-run          Build and run the full containerized scraper workflow
	@echo   docker-profile      Create or refresh the browser profile inside Docker
	@echo   docker-scrape       Run the scraper inside Docker without reseeding
	@echo   docker-analysis     Run analytics inside Docker
	@echo   docker-seed         Seed product targets inside Docker
	@echo   docker-test         Run unit tests inside Docker
	@echo   docker-shell        Open a shell inside the Docker runtime
	@echo   lint                Run Ruff lint checks
	@echo   format              Format Python files with Ruff
	@echo   format-check        Check Python formatting
	@echo   fix                 Apply Ruff lint fixes and formatting
	@echo   type-check          Run Pyright static type checks
	@echo   test                Run unit tests
	@echo   test-cov            Run unit tests with coverage gate
	@echo   pip-check           Verify installed package dependency metadata
	@echo   pre-commit          Run pre-commit hooks across the repository
	@echo   pre-commit-install  Install Git pre-commit hooks
	@echo   validate            Run local non-mutating quality checks
	@echo   ci                  Run the CI validation target

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install .

install-dev:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install ".[dev]"

lint:
	$(PYTHON) -m ruff check $(SRC_DIRS)

format:
	$(PYTHON) -m ruff format $(SRC_DIRS)

format-check:
	$(PYTHON) -m ruff format --check $(SRC_DIRS)

fix:
	$(PYTHON) -m ruff check --fix $(SRC_DIRS)
	$(PYTHON) -m ruff format $(SRC_DIRS)

type-check:
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest $(UNIT_TESTS) -q

test-cov:
	$(PYTHON) -m pytest $(UNIT_TESTS) -v --tb=short --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

pip-check:
	$(PYTHON) -m pip check

pre-commit:
	$(PYTHON) -m pre_commit run --all-files --show-diff-on-failure

pre-commit-install:
	$(PYTHON) -m pre_commit install

validate: lint format-check type-check pip-check test-cov

ci: pre-commit type-check pip-check test-cov

profile:
	$(PYTHON) -m src.tasks.create_profile

seed:
	$(PYTHON) -m src.tasks.seed_targets --file $(SEED_FILE)

run:
	$(PYTHON) -m src.main

analysis:
	$(PYTHON) -m src.analysis.main

docker-config:
	$(DOCKER_COMPOSE) config

docker-build:
	$(DOCKER_COMPOSE) build

docker-prod-build:
	$(DOCKER) build --target production -t $(PROD_IMAGE_NAME) .

docker-run:
	$(DOCKER_COMPOSE) up --build $(COMPOSE_SERVICE)

docker-profile:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) profile

docker-seed:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) seed

docker-scrape:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) scrape

docker-analysis:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) analysis

docker-test:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) test

docker-shell:
	$(DOCKER_COMPOSE) run --rm $(COMPOSE_SERVICE) bash
