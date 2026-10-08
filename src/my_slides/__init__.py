"""Local investment wiki and presentation workflow."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def _read_version() -> str:
    """Prefer pyproject.toml so editable checkouts track git pull without reinstall."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        value = data.get("project", {}).get("version")
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        return package_version("my-slides")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _read_version()
