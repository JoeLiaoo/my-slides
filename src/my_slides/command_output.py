"""Human and JSON output shared by CLI commands."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def emit(args: argparse.Namespace, data: dict[str, Any], human: str, error: bool = False) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(human, file=sys.stderr if error else sys.stdout)
