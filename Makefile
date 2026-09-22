.PHONY: install test lint format format-check typecheck run

PYTHON ?= python

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m black .

format-check:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m black --check .

typecheck:
	$(PYTHON) -m mypy

run:
	$(PYTHON) -m uvicorn atlaspipe.api.app:create_app --factory --host 0.0.0.0 --port 8000
