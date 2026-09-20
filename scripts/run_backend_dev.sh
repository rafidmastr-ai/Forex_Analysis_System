#!/usr/bin/env bash
# Linux Cloud development — mock data adapter, no MT5 involved.
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV=dev
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
