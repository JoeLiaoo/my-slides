"""Project configuration and v2 workspace helpers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .units import detect_format_version, slug

APP_DIR = "my-slides"
V1_UNSUPPORTED_MESSAGE = (
    "当前项目没有 my-slides/units.json，已不再支持 v1 章节格式。"
    "旧版章节迁移（migrate）已移除；请重新 `my-slides init` 创建 v2 项目。"
)


def require_v2_project(base: Path) -> None:
    """Daily workflow requires units.json (v2 only)."""
    if detect_format_version(base) != "v2":
        raise ValueError(V1_UNSUPPORTED_MESSAGE)


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def find_slug_collisions(chapters: list[str]) -> list[str]:
    """Detect chapter titles that collapse to the same filesystem slug."""
    by_slug: dict[str, list[str]] = {}
    for chapter in chapters:
        by_slug.setdefault(slug(chapter), []).append(chapter)
    errors: list[str] = []
    for value, names in by_slug.items():
        if len(names) > 1:
            errors.append(f"章节 slug 冲突「{value}」：{'、'.join(names)}（请改名使 slug 唯一）")
    return errors


def strip_yaml_trailing_comment(value: str) -> str:
    """Remove an unquoted trailing # comment from a YAML scalar."""
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value


def project_root(value: str | None, *, discover: bool = True) -> Path:
    if value:
        root = Path(value).expanduser().resolve()
    else:
        start = Path.cwd().resolve()
        root = start
        if discover:
            for candidate in (start, *start.parents):
                if (candidate / APP_DIR / "project.yaml").is_file():
                    root = candidate
                    break
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{root}")
    return root


def app_path(root: Path) -> Path:
    return root / APP_DIR


def read_config(path: Path) -> dict[str, Any]:
    """Read the small, list-based YAML subset written by this CLI.

    Supports only the shape this tool writes: scalar keys and block lists under
    ``source_dirs`` / ``chapters``. Inline lists like ``chapters: [a, b]`` are
    rejected with a Chinese error instead of being misread character-by-character.
    """
    config: dict[str, Any] = {"source_dirs": ["."], "chapters": []}
    current_list: str | None = None
    if not path.exists():
        return config
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list:
            item = strip_yaml_trailing_comment(stripped[2:].strip()).strip().strip("\"'")
            if not item:
                raise ValueError(f"project.yaml 第 {line_no} 行：列表项不能为空")
            config[current_list].append(item)
            continue
        current_list = None
        match = re.match(r"([\w-]+):\s*(.*)$", stripped)
        if not match:
            raise ValueError(
                f"project.yaml 第 {line_no} 行无法解析：{stripped}。"
                "请使用 key: value 或章节列表格式（每行一个 `- 名称`）"
            )
        key, value = match.groups()
        value = strip_yaml_trailing_comment(value).strip()
        if key in {"source_dirs", "chapters"}:
            if not value:
                config[key] = []
                current_list = key
                continue
            if value.startswith("["):
                raise ValueError(
                    f"project.yaml 的 {key} 不支持行内列表写法（如 {key}: [a, b]）。"
                    f"请写成：\n{key}:\n  - \"章节名\""
                )
            raise ValueError(
                f"project.yaml 的 {key} 必须是列表，请写成：\n{key}:\n  - \"名称\""
            )
        if value:
            config[key] = value.strip("\"'")
    for key in ("source_dirs", "chapters"):
        if not isinstance(config.get(key), list):
            raise ValueError(f"project.yaml 的 {key} 必须是列表")
    collisions = find_slug_collisions([str(item) for item in config.get("chapters", [])])
    if collisions:
        raise ValueError("；".join(collisions))
    return config


def write_config(
    path: Path,
    root: Path,
    source_dirs: list[str],
    chapters: list[str],
    brand_color: str = "#A6192E",
    *,
    approval_mode: str | None = None,
    reviewer: str | None = None,
) -> None:
    clean = lambda value: value.replace('"', "")
    lines = [f'project: "{clean(root.name)}"', f'brand_color: "{brand_color}"', "source_dirs:"]
    lines.extend(f'  - "{clean(d)}"' for d in source_dirs)
    lines.append("chapters:")
    lines.extend(f'  - "{clean(chapter)}"' for chapter in chapters)
    if approval_mode:
        mode = str(approval_mode).strip()
        if mode not in {"chat", "terminal"}:
            raise ValueError("project.yaml 的 approval_mode 必须是 chat 或 terminal")
        lines.append(f'approval_mode: "{mode}"')
    if reviewer and str(reviewer).strip():
        lines.append(f'reviewer: "{clean(str(reviewer).strip())}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def template_chapters() -> list[str]:
    repository_template = Path(__file__).resolve().parents[2] / "docs" / "templates" / "投资报告章节.md"
    packaged_template = Path(__file__).parent / "templates" / "investment-report-chapters.md"
    template = repository_template if repository_template.exists() else packaged_template
    return re.findall(r"^##\s+(.+?)\s*$", template.read_text(encoding="utf-8"), flags=re.MULTILINE)


def ensure_project(root: Path) -> tuple[Path, dict[str, Any]]:
    base = app_path(root)
    cfg = read_config(base / "project.yaml")
    if not (base / "project.yaml").exists():
        raise ValueError(f"项目尚未初始化，请先运行 my-slides init --project {root}")
    return base, cfg
