#!/usr/bin/env bash
# Full local regression: also runs the Design+Slides engine integration tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Ask Python for the path form and separator so Git Bash on Windows works too.
SRC="$(python3 -c 'import os; print(os.path.abspath("src"))')"
SEP="$(python3 -c 'import os; print(os.pathsep)')"
export PYTHONPATH="$SRC${PYTHONPATH:+$SEP$PYTHONPATH}"

echo "==> Checking Design+Slides engine (MY_SLIDES_DESIGN_ROOT)"
python3 -c 'import json, sys
from my_slides.design_engine import design_status
status = design_status()
print(json.dumps(status, ensure_ascii=False, indent=2))
sys.exit(0 if status["ready"] else 1)' || {
  echo "Design+Slides engine not ready: set MY_SLIDES_DESIGN_ROOT, then npm install && npm run build in it." >&2
  exit 1
}

echo "==> Checking skill template mirrors"
python3 scripts/sync-skill-templates.py --check

echo "==> Running full unittest suite"
python3 -m unittest discover -s tests -v

echo "==> Full local tests passed."
