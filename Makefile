.PHONY: install up down migrate test lint format format-check typecheck benchmark seed run

PYTHON ?= python

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

up:
	docker compose up --build

down:
	docker compose down

migrate:
	$(PYTHON) -m alembic upgrade head

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

benchmark:
	$(PYTHON) benchmarks/ingestion_benchmark.py
	$(PYTHON) benchmarks/database_benchmark.py

seed:
	$(PYTHON) scripts/seed.py

run:
	$(PYTHON) -m uvicorn atlaspipe.api.app:create_app --factory --host 0.0.0.0 --port 8000
