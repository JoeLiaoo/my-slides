#!/usr/bin/env bash
# Fast local suite: Design+Slides engine integration tests skip without MY_SLIDES_DESIGN_ROOT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Ask Python for the path form and separator so Git Bash on Windows works too.
SRC="$(python3 -c 'import os; print(os.path.abspath("src"))')"
SEP="$(python3 -c 'import os; print(os.pathsep)')"
export PYTHONPATH="$SRC${PYTHONPATH:+$SEP$PYTHONPATH}"

python3 -m unittest discover -s tests -v
echo "==> Quick tests finished (skipped Design engine cases are OK)."
