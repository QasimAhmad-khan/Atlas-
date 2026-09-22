.PHONY: install up down migrate test lint format format-check typecheck benchmark domain-rollup-benchmark frontier-demo postgres-frontier-demo worker-death-demo seed run

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

domain-rollup-benchmark:
	$(PYTHON) benchmarks/domain_rollup_benchmark.py

frontier-demo:
	$(PYTHON) scripts/frontier_recovery_demo.py

postgres-frontier-demo:
	$(PYTHON) scripts/postgres_frontier_recovery_demo.py

worker-death-demo:
	$(PYTHON) scripts/postgres_worker_death_demo.py

seed:
	$(PYTHON) scripts/seed.py

run:
	$(PYTHON) -m uvicorn atlaspipe.api.app:create_app --factory --host 0.0.0.0 --port 8000
