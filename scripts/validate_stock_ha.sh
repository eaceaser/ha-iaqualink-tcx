#!/bin/sh
# Isolated offline-vendor validation; no HA config or credentials are mounted.
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker run --rm \
  -v "$repo_dir:/work:ro" -e PYTHONPATH=/work -e RUFF_CACHE_DIR=/tmp/ruff-cache -e PYTHONDONTWRITEBYTECODE=1 -w /work \
  --entrypoint /bin/sh \
  ghcr.io/home-assistant/home-assistant:2026.11.0@sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e \
  -ec '
    python -m pip install -c /usr/src/homeassistant/homeassistant/package_constraints.txt -r requirements-dev.txt
    python -m ruff check custom_components tests scripts
    python -m ruff format --check custom_components tests scripts
    python -m pytest -q -p no:cacheprovider
    python scripts/stock_ha_smoke.py
  '
