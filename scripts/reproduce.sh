#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON:-python3}"
records="${ATLASPIPE_DEMO_RECORDS:-10000}"
batch_size="${ATLASPIPE_DEMO_BATCH_SIZE:-500}"
concurrency="${ATLASPIPE_DEMO_CONCURRENCY:-50}"

if [ ! -d ".venv" ]; then
  "$python_bin" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
python scripts/frontier_recovery_demo.py \
  --records "$records" \
  --batch-size "$batch_size" \
  --concurrency "$concurrency"
