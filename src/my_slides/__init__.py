"""Local investment wiki and presentation workflow."""

from __future__ import annotations

import subprocess
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


def git_metadata(repo_path: Path | None = None) -> tuple[str | None, bool | None]:
    """Return the source checkout's short commit and dirty state when available.

    A normal wheel has no project ``pyproject.toml`` next to the package, so it
    keeps reporting only the installed package version. Git failures are also
    deliberately non-fatal for packaged installs and restricted environments.
    """
    source_root = (repo_path or Path(__file__).resolve().parents[2]).resolve()
    project_file = source_root / "pyproject.toml"
    if not project_file.is_file():
        return None, None
    try:
        import tomllib

        project = tomllib.loads(project_file.read_text(encoding="utf-8")).get("project")
        if not isinstance(project, dict) or project.get("name") != "my-slides":
            return None, None
        root_result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
        )
        git_root = Path(root_result.stdout.strip()).resolve()
        source_root.relative_to(git_root)
        commit_result = subprocess.run(
            ["git", "-C", str(git_root), "rev-parse", "--short=7", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
        )
        status_result = subprocess.run(
            ["git", "-C", str(git_root), "status", "--porcelain", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    commit = commit_result.stdout.strip()
    if not commit:
        return None, None
    return commit, bool(status_result.stdout.strip())


def version_metadata() -> dict[str, str | bool | None]:
    commit, dirty = git_metadata()
    return {"version": __version__, "commit": commit, "dirty": dirty}


def format_version(program: str = "my-slides") -> str:
    metadata = version_metadata()
    text = f"{program} {metadata['version']}"
    if metadata["commit"]:
        detail = str(metadata["commit"])
        if metadata["dirty"]:
            detail += ", 有未提交修改"
        text += f" ({detail})"
    return text
