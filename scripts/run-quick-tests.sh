#!/usr/bin/env bash
# Fast local suite: no renderer/browser install; optional deps may skip.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-}:$ROOT/src"
unset MY_SLIDES_FULL_TESTS || true

python3 -m unittest discover -s tests -v
echo "==> Quick tests finished (skipped optional renderer/browser cases are OK)."
