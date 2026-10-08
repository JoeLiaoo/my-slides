#!/usr/bin/env bash
# Local full regression for my-slides (Phase 10).
# Does NOT use GitHub Actions — run this on a machine with Node + network for installs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-}:$ROOT/src"
export MY_SLIDES_FULL_TESTS=1

if [[ -z "${MY_SLIDES_RENDERER_HOME:-}" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    export MY_SLIDES_RENDERER_HOME="${HOME}/Library/Application Support/MySlides/renderer"
  else
    export MY_SLIDES_RENDERER_HOME="${LOCALAPPDATA:-${HOME}/.local/share}/MySlides/renderer"
  fi
fi

echo "==> Installing pinned renderer (ECharts / Lucide)"
python3 -m my_slides.cli renderer install

echo "==> Installing Playwright Chromium"
python3 -m my_slides.cli browser install

echo "==> Running full unittest suite (skips become failures via MY_SLIDES_FULL_TESTS=1)"
python3 -m unittest discover -s tests -v

echo "==> Full local tests passed."
