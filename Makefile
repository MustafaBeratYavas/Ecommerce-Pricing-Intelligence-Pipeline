.DEFAULT_GOAL := help

PYTHON ?= python
SEED_FILE ?= product_codes.txt
COVERAGE_MIN ?= 80
export PRE_COMMIT_HOME ?= .pre-commit-cache

SRC_DIRS := src tests
UNIT_TESTS := tests/unit

.PHONY: help install install-dev lint format format-check fix test test-cov pip-check pre-commit pre-commit-install check-launcher validate ci profile seed run analysis

help:
	@echo "Available targets:"
	@echo "  install             Install runtime dependencies"
	@echo "  install-dev         Install runtime and development dependencies"
	@echo "  lint                Run Ruff lint checks"
	@echo "  format              Format Python files with Ruff"
	@echo "  format-check        Check Python formatting"
	@echo "  fix                 Apply Ruff lint fixes and formatting"
	@echo "  test                Run unit tests"
	@echo "  test-cov            Run unit tests with coverage gate"
	@echo "  pip-check           Verify installed package dependency metadata"
	@echo "  pre-commit          Run pre-commit hooks across the repository"
	@echo "  pre-commit-install  Install Git pre-commit hooks"
	@echo "  validate            Run local non-mutating quality checks"
	@echo "  ci                  Run the CI validation target"
	@echo "  profile             Create or refresh the browser profile"
	@echo "  seed                Seed product targets from SEED_FILE"
	@echo "  run                 Run the scraping pipeline"
	@echo "  analysis            Run the strategic analytics engine"

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

check-launcher:
	$(PYTHON) -c "import os, shutil, subprocess, sys; bash = shutil.which('bash'); skip = os.name == 'nt' or bash is None; print('Skipping start.sh syntax check on this platform') if skip else None; sys.exit(0 if skip else subprocess.run([bash, '-n', 'start.sh'], check=False).returncode)"

validate: lint format-check pip-check test-cov

ci: check-launcher pre-commit pip-check test-cov

profile:
	$(PYTHON) -m src.tasks.create_profile

seed:
	$(PYTHON) -m src.tasks.seed_targets --file $(SEED_FILE)

run:
	$(PYTHON) -m src.main

analysis:
	$(PYTHON) -m src.analysis.main
