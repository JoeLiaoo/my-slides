"""Inspect or install the pinned local SVG renderer."""

from __future__ import annotations

import argparse
import json

from ..command_output import emit
from ..rendering import install_renderers, renderer_status


def run(args: argparse.Namespace) -> int:
    status = install_renderers() if args.renderer_command == "install" else renderer_status()
    emit(args, status, json.dumps(status, ensure_ascii=False, indent=2), error=not status["ready"])
    return 0 if status["ready"] else 1
