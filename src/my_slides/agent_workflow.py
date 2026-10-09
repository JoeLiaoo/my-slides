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
