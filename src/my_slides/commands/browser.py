"""Inspect or install the offline browser runtime."""

from __future__ import annotations

import argparse
import json

from ..browser_runtime import browser_status, install_browser
from ..command_output import emit


def run(args: argparse.Namespace) -> int:
    status = install_browser() if args.browser_command == "install" else browser_status()
    ok = status["playwright"] and status["chromium_installed"]
    emit(args, status, json.dumps(status, ensure_ascii=False, indent=2), error=not ok)
    return 0 if ok else 1
