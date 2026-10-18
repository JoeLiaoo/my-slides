"""Install the bundled project workflow skill."""
from __future__ import annotations

import shutil
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any


def install_agent_workflow(root: Path) -> dict[str, Any]:
    """Install the bundled workflow skill without replacing user edits."""
    repository_skill = Path(__file__).resolve().parents[2] / "skills" / "my-slides-workflow" / "SKILL.md"
    packaged_skill = Path(str(package_files("my_slides").joinpath("templates", "my-slides-workflow.md")))
    source = repository_skill if repository_skill.is_file() else packaged_skill
    if not source.is_file():
        raise FileNotFoundError("安装包缺少 my-slides-workflow 技能文件")
    installed: list[str] = []
    preserved: list[str] = []
    for parent in (root / ".agents" / "skills", root / ".claude" / "skills"):
        destination = parent / "my-slides-workflow" / "SKILL.md"
        if destination.exists():
            preserved.append(destination.relative_to(root).as_posix())
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        installed.append(destination.relative_to(root).as_posix())
    return {"installed": installed, "preserved": preserved}


def check_agent_workflow(root: Path) -> dict[str, Any]:
    """Compare installed Agent workflow files with this package's authoritative copy."""
    repository_skill = Path(__file__).resolve().parents[2] / "skills" / "my-slides-workflow" / "SKILL.md"
    packaged_skill = Path(str(package_files("my_slides").joinpath("templates", "my-slides-workflow.md")))
    source = repository_skill if repository_skill.is_file() else packaged_skill
    if not source.is_file():
        raise FileNotFoundError("安装包缺少 my-slides-workflow 技能文件")
    expected = source.read_bytes()
    files = []
    for parent in (root / ".agents" / "skills", root / ".claude" / "skills"):
        destination = parent / "my-slides-workflow" / "SKILL.md"
        if destination.is_symlink():
            state = "unsafe_symlink"
        elif not destination.is_file():
            state = "missing"
        else:
            try: state = "current" if destination.read_bytes() == expected else "outdated"
            except OSError: state = "unreadable"
        files.append({"path": destination.relative_to(root).as_posix(), "status": state})
    return {"ok": all(item["status"] == "current" for item in files), "files": files}
