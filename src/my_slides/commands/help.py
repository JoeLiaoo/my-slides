"""Print the bundled agent workflow guide."""

from __future__ import annotations

import argparse
from importlib.resources import files as package_files

from .. import version_metadata
from ..command_output import emit


def run(args: argparse.Namespace) -> int:
    guide = package_files("my_slides").joinpath("templates", "agent-help.md").read_text(encoding="utf-8").strip()
    emit(args, {**version_metadata(), "guide": guide}, guide)
    return 0
