#!/usr/bin/env bash
# Fast local thin-workspace suite; no Design+Slides engine required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Ask Python for the path form and separator so Git Bash on Windows works too.
SRC="$(python3 -c 'import os; print(os.path.abspath("src"))')"
SEP="$(python3 -c 'import os; print(os.pathsep)')"
export PYTHONPATH="$SRC${PYTHONPATH:+$SEP$PYTHONPATH}"

python3 -m unittest discover -s tests -v
echo "==> Quick tests passed."
