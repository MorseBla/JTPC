#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$HERE/../.." && pwd)"
PYTHON="${PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then PYTHON=python3; fi
export MPLBACKEND=Agg
exec "$PYTHON" "$HERE/plotting.py"
