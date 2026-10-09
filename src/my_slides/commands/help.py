"""Print the bundled agent workflow guide."""

from __future__ import annotations

import argparse
from importlib.resources import files as package_files

from .. import __version__
from ..command_output import emit


def run(args: argparse.Namespace) -> int:
    guide = package_files("my_slides").joinpath("templates", "agent-help.md").read_text(encoding="utf-8").strip()
    emit(args, {"version": __version__, "guide": guide}, guide)
    return 0
