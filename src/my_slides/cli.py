from __future__ import annotations

import argparse
import html
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from importlib.resources import files as package_files
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .state import collect_units_status
from .unit_workflow import (
    approve_unit_report,
    approve_unit_spec,
    assemble_after_report_approvals,
    prepare_unit_handoff,
    resolve_unit_selection,
    validate_unit_report,
    validate_unit_spec,
)
from .units import (
    MARKDOWN_LINK_RE,
    Unit,
    UnitsError,
    detect_format_version,
    ensure_v2_directories,
    list_units_status,
    load_units_manifest,
    migrate_to_units,
    migrate_to_units_preview,
    resolve_local_markdown_path,
    rollback_units_migration,
    unit_id_prefix,
)

APP_DIR = "my-slides"
V2_UNSUPPORTED_CHAPTER_ACTIONS = frozenset({
    "prepare report",
    "prepare spec",
    "prepare slides",
    "validate report",
    "validate spec",
    "approve report",
    "approve spec",
    "slides build",
    "slides check",
})

V1_UNSUPPORTED_MESSAGE = (
    "当前项目没有 my-slides/units.json，已不再支持 v1 章节格式。"
    "请用仍含迁移功能的版本运行 `my-slides migrate --to-units --dry-run` 预检后，"
    "再执行 `my-slides migrate --to-units`；或从 `.state/migrate-backups/` 回滚后使用旧版工具。"
    "新项目请重新 `my-slides init`（仅创建 v2）。"
)


def require_v2_project(base: Path) -> None:
    """Phase 9: daily workflow requires units.json. Migrate remains the escape hatch."""
    if detect_format_version(base) != "v2":
        raise ValueError(V1_UNSUPPORTED_MESSAGE)


def refuse_unsupported_v2_action(base: Path, action: str, *, unit_mode: bool = False) -> None:
    """v2 projects reject chapter-wide approve/build unless a unit selector is used."""
    require_v2_project(base)
    if action not in V2_UNSUPPORTED_CHAPTER_ACTIONS:
        return
    if unit_mode and action in {
        "prepare report",
        "prepare spec",
        "prepare slides",
        "validate report",
        "validate spec",
        "approve report",
        "approve spec",
        "slides build",
        "slides check",
    }:
        return
    raise ValueError(
        f"当前项目为 v2 单元格式，不支持章节级命令：{action}。"
        "请改用带 --unit / --changed / --all 的单元命令。"
    )


def v2_unit_mode(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "units", None) or getattr(args, "changed", False) or getattr(args, "all_units", False))
EXCLUDED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__"}
EXCLUDED_FILES = {"agents.md", "claude.md", "gemini.md", "copilot-instructions.md"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slug(value: str) -> str:
    value = re.sub(r"[^\w\u3400-\u9fff.-]+", "-", value.strip().lower(), flags=re.UNICODE)
    return value.strip("-.") or "section"


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


def write_config(path: Path, root: Path, source_dirs: list[str], chapters: list[str], brand_color: str = "#A6192E") -> None:
    clean = lambda value: value.replace('"', "")
    lines = [f'project: "{clean(root.name)}"', f'brand_color: "{brand_color}"', "source_dirs:"]
    lines.extend(f'  - "{clean(d)}"' for d in source_dirs)
    lines.append("chapters:")
    lines.extend(f'  - "{clean(chapter)}"' for chapter in chapters)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def template_chapters() -> list[str]:
    repository_template = Path(__file__).resolve().parents[2] / "docs" / "templates" / "投资报告章节.md"
    packaged_template = Path(__file__).parent / "templates" / "investment-report-chapters.md"
    template = repository_template if repository_template.exists() else packaged_template
    return re.findall(r"^##\s+(.+?)\s*$", template.read_text(encoding="utf-8"), flags=re.MULTILINE)


def report_template_text() -> str:
    repository_template = Path(__file__).resolve().parents[2] / "docs" / "templates" / "投资报告章节.md"
    packaged_template = Path(__file__).parent / "templates" / "investment-report-chapters.md"
    template = repository_template if repository_template.exists() else packaged_template
    return template.read_text(encoding="utf-8").strip()


def wiki_instructions() -> str:
    return """# Wiki 维护约定

本 Wiki 是项目持续积累的 Markdown 知识库。请先读 index.md，再按主题页阅读和更新知识；新资料到来时将内容整合进相关页面，补充页面间链接，更新索引，并在 log.md 追加简短记录。有价值的问答、比较和综合分析也可以沉淀为新页面。

使用自然语言和普通 Markdown。无需 frontmatter、固定标签、逐条事实分类或资料 ID。重要判断、数字口径、预测假设和不确定性在相关正文中直接说明。引用使用相对 Markdown 链接，尽量链接到原始资料或相关 Wiki 页面；从 Wiki 链接到项目根目录资料时，按页面所在层级计算相对路径。原始项目资料由 agent 只读。

索引按项目报告章节组织；同一主题页面可以出现在多个章节下。维护 Wiki 时顺手检查断链、过期信息、口径冲突、重复页面及缺少的关联。遇到矛盾时保留各自语境并用简洁文字指出待核实之处。
"""


def sync_wiki_index(path: Path, chapters: list[str]) -> None:
    if not path.exists():
        parts = [
            "# Wiki Index",
            "",
            "项目知识导航按报告章节组织。将相关主题页面链接放在对应章节下；同一页面允许出现在多个章节。",
            "",
        ]
        for chapter in chapters:
            parts.extend([f"## {chapter}", "", "<!-- 列出本章相关 Wiki 页面及一句话说明。 -->", ""])
        parts.extend(["## 补充研究", "", "<!-- 列出尚未纳入报告章节的研究页面。 -->", ""])
        path.write_text("\n".join(parts), encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8")
    headings = set(re.findall(r"^##\s+(.+?)\s*$", content, flags=re.MULTILINE))
    missing = [chapter for chapter in chapters if chapter not in headings]
    if not missing:
        return
    additions = "\n".join(f"## {chapter}\n\n<!-- 列出本章相关 Wiki 页面及一句话说明。 -->\n" for chapter in missing)
    extra_heading = re.search(r"^## 补充研究\s*$", content, flags=re.MULTILINE)
    if extra_heading:
        content = content[:extra_heading.start()] + additions + "\n" + content[extra_heading.start():]
    else:
        content = content.rstrip() + "\n\n" + additions + "\n## 补充研究\n\n<!-- 列出尚未纳入报告章节的研究页面。 -->\n"
    path.write_text(content, encoding="utf-8")


def ensure_project(root: Path) -> tuple[Path, dict[str, Any]]:
    base = app_path(root)
    cfg = read_config(base / "project.yaml")
    if not (base / "project.yaml").exists():
        raise ValueError(f"项目尚未初始化，请先运行 my-slides init --project {root}")
    return base, cfg


def discover_sources(root: Path, cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    app = app_path(root).resolve()
    found: dict[str, dict[str, Any]] = {}
    for entry in cfg.get("source_dirs", ["."]):
        candidate = (root / entry).resolve()
        if not candidate.is_dir():
            continue
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        for path in candidate.rglob("*.md"):
            if app in path.parents or path.name.lower() in EXCLUDED_FILES:
                continue
            if any(part.lower() in EXCLUDED_DIRS or part.startswith(".") for part in path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            found[rel] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    return found


def source_digest(root: Path, cfg: dict[str, Any]) -> str:
    current = discover_sources(root, cfg)
    payload = json.dumps(sorted((path, item["sha256"]) for path, item in current.items()), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scan_sources(root: Path, base: Path, cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    state_path = base / ".state" / "sources.json"
    old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"files": {}}
    current = discover_sources(root, cfg)
    previous = old.get("files", {})
    pending: list[str] = []
    removed: list[str] = []
    merged: dict[str, Any] = {}
    for name, value in current.items():
        prior = previous.get(name, {})
        ingested = prior.get("ingested_sha256")
        merged[name] = {**value, "ingested_sha256": ingested}
        if ingested != value["sha256"]:
            pending.append(name)
    for name, prior in previous.items():
        if name not in current:
            merged[name] = {**prior, "removed": True}
            if not prior.get("removed_acknowledged_at"):
                removed.append(name)
    state = {"scanned_at": now(), "files": merged}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state, sorted(pending), sorted(removed)


def mark_ingested(base: Path, names: list[str] | None = None) -> int:
    path = base / ".state" / "sources.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"files": {}}
    selected = set(names or state["files"].keys())
    count = 0
    for name, item in state["files"].items():
        if name in selected and item.get("removed") and not item.get("removed_acknowledged_at"):
            item["removed_acknowledged_at"] = now()
            count += 1
        elif name in selected and not item.get("removed"):
            item["ingested_sha256"] = item["sha256"]
            count += 1
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def snapshot_wiki(base: Path, stamp: str) -> Path:
    source = base / "wiki"
    target = base / ".state" / "snapshots" / "wiki" / stamp
    records = []
    for page in source.rglob("*.md"):
        relative = page.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = page.read_bytes()
        destination.write_bytes(content)
        records.append({"path": relative.as_posix(), "sha256": hashlib.sha256(content).hexdigest()})
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(json.dumps({"captured_at": now(), "files": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def snapshot_approved_revision(base: Path, cfg: dict[str, Any], kind: str, digest: str) -> Path:
    folder = base / ("reports" if kind == "report" else "specs")
    target = base / ".state" / "revisions" / kind / digest
    target.mkdir(parents=True, exist_ok=True)
    files = []
    for chapter in cfg.get("chapters", []):
        source = folder / f"{slug(chapter)}.md"
        content = source.read_bytes()
        (target / source.name).write_bytes(content)
        files.append({"path": source.name, "sha256": hashlib.sha256(content).hexdigest()})
    (target / "manifest.json").write_text(json.dumps({"kind": kind, "approved_sha256": digest, "captured_at": now(), "files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def init_project(args: argparse.Namespace) -> int:
    root = project_root(args.project, discover=False)
    base = app_path(root)
    cfg_path = base / "project.yaml"
    if cfg_path.exists() and not args.force:
        raise ValueError(f"项目已初始化：{base}（如需补全结构并重写配置，请使用 --force）")
    existing = read_config(cfg_path)
    source_dirs = args.source_dir or existing.get("source_dirs") or ["."]
    chapters = existing.get("chapters") or template_chapters()
    brand_color = existing.get("brand_color", "#A6192E")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        raise ValueError("project.yaml 的 brand_color 必须是 #RRGGBB 格式")
    # Phase 9: only v2. Ignore legacy --format if still passed by older scripts.
    base.mkdir(parents=True, exist_ok=True)
    for folder in ("research", "wiki", "reports", "specs", "slides", ".state"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    wiki_readme = base / "wiki" / "README.md"
    if not wiki_readme.exists():
        wiki_readme.write_text(wiki_instructions(), encoding="utf-8")
    index = base / "wiki" / "index.md"
    sync_wiki_index(index, chapters)
    log = base / "wiki" / "log.md"
    if not log.exists():
        log.write_text(f"# Wiki Log\n\n## {now()} | 初始化\n\n建立项目 Wiki 目录与章节索引。\n", encoding="utf-8")
    for folder, title in (("reports", "投资报告"), ("specs", "Presentation Specs"), ("slides", "HTML Slides")):
        readme = base / folder / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {title}\n\n由当前 agent 按项目 Wiki 与 units.json 单元清单生成内容。\n",
                encoding="utf-8",
            )
    write_config(cfg_path, root, source_dirs, chapters, brand_color)
    ensure_v2_directories(base)
    seed = [
        Unit(id="cover", chapter=chapters[0], role="cover"),
        *[
            Unit(
                id=f"{unit_id_prefix(chapter, fallback=f'chapter-{index:02d}')}-01",
                chapter=chapter,
                role="content",
            )
            for index, chapter in enumerate(chapters, start=1)
        ],
    ]
    seen: set[str] = set()
    unique: list[Unit] = []
    for unit in seed:
        unit_id = unit.id
        suffix = 2
        while unit_id in seen:
            unit_id = f"{unit.id}-{suffix}"
            suffix += 1
        seen.add(unit_id)
        unique.append(Unit(id=unit_id, chapter=unit.chapter, role=unit.role))
    from .units import write_units_manifest

    write_units_manifest(base, unique)
    unit_ids = [unit.id for unit in unique]
    _, pending, removed = scan_sources(root, base, read_config(cfg_path))
    result = {
        "project": str(root),
        "workspace": str(base),
        "chapters": chapters,
        "format_version": "v2",
        "units": unit_ids,
        "pending_sources": pending,
        "removed_sources": removed,
        "deprecated": False,
    }
    human = (
        f"已初始化项目工作区：{base}\n报告章节主题：{len(chapters)}\n"
        f"格式：v2（{len(unit_ids)} 个种子单元）\n待整理 Markdown：{len(pending)}"
    )
    emit(args, result, human)
    return 0


def prepare(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    kind = args.kind
    if kind in {"report", "spec", "slides"}:
        require_v2_project(base)
        refuse_unsupported_v2_action(base, f"prepare {kind}", unit_mode=v2_unit_mode(args))
        units = resolve_unit_selection(
            base,
            cfg,
            unit_ids=getattr(args, "units", None),
            changed=bool(getattr(args, "changed", False)),
            all_units=bool(getattr(args, "all_units", False)),
        )
        if kind == "report":
            _, pending, removed = scan_sources(root, base, cfg)
            if pending or removed:
                raise ValueError("请先整理有变化或已移除的资料，并运行 my-slides sources mark-ingested")
            wiki_errors = validate_wiki(base, cfg)
            if wiki_errors:
                raise ValueError("请先修复 Wiki 链接：" + "；".join(wiki_errors))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        if kind == "report":
            snapshot_wiki(base, stamp)
        output = prepare_unit_handoff(base, root, units, kind, stamp=stamp)
        emit(
            args,
            {"task_file": str(output), "kind": kind, "units": [u.id for u in units], "deprecated": False},
            f"已生成单元交接材料：{output}",
        )
        return 0
    out_dir = base / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = out_dir / f"{stamp}-{kind}.md"
    chapters = cfg.get("chapters", [])
    common = f"项目目录：{root}\n工作区：{base}\n章节顺序：" + "、".join(chapters)
    if kind == "wiki":
        if args.question:
            body = f"""# Wiki 问答任务

{common}

## 用户问题
{args.question}

先阅读 wiki/README.md 和 wiki/index.md，按索引找到相关页面并核对内容，再综合回答。回答中的结论应附上相关 Wiki 页面或原始资料链接；说明来源之间存在的差异和未解决的问题。只在用户明确要求沉淀时才新建或更新 Wiki 页面，并同步维护 index.md 和 log.md。
"""
        else:
            _, pending, removed = scan_sources(root, base, cfg)
            todo = "\n".join(f"- {p}" for p in pending) or "- 当前没有新增或修改的 Markdown 资料。"
            gone = "\n".join(f"- {p}" for p in removed) or "- 无。"
            body = f"""# Wiki 整理任务

{common}

先阅读 wiki/README.md、wiki/index.md 和近期 wiki/log.md。按 Karpathy LLM Wiki 的方式把新增资料整合进已有主题页，维护页面间链接、按章节更新 index，并向 log 追加记录。使用普通 Markdown 与可读链接，不添加固定标签、frontmatter 或来源 ID。链接项目根目录下的源资料时，按源文件所在 Wiki 页面的位置计算相对路径。完成后运行 my-slides sources mark-ingested。

## 待整理资料
{todo}

## 已删除或移出扫描范围的资料
{gone}

原始资料保持只读。若资料之间存在口径冲突，在相关页面用自然语言记下差异和待核实问题。
"""
    else:
        raise ValueError(f"未知 prepare 类型：{kind}")
    output.write_text(body, encoding="utf-8")
    emit(args, {"task_file": str(output), "kind": kind, "deprecated": False}, f"已生成交接材料：{output}")
    return 0


def strip_markdown_link_target(raw: str) -> str:
    """Normalize a Markdown destination: drop optional title and angle brackets."""
    target = (raw or "").strip()
    if target.startswith("<") and ">" in target:
        inner, _, rest = target[1:].partition(">")
        target = inner.strip()
        rest = rest.strip()
        if rest:
            # Title after angled destination — ignore it.
            pass
        return target
    # destination "title" or destination 'title' or destination (title)
    match = re.match(
        r'^(.*?)(?:\s+(?:"(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\'|\((?:\\.|[^)])*\)))\s*$',
        target,
    )
    if match and match.group(1).strip():
        return match.group(1).strip()
    return target


def strip_markdown_code_regions(text: str) -> str:
    """Blank out fenced and inline code so link finders ignore pseudo-links inside."""
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", " ", text)


def markdown_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = strip_markdown_code_regions(path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        label = match.group(0)
        # Footnote references look like [^1]; definitions are handled as ref-defs.
        if re.match(r"^\[\^[^\]]+\]", label):
            continue
        targets.append(strip_markdown_link_target(match.group(1)))
    return targets


def extract_approved_icons(icon_section: str) -> set[str]:
    """Parse Spec「图标需求」into Lucide kebab-case names.

    Only an entire section that is exactly「无」means no icons. List items
    (``- name``) are preferred; comma-separated tokens are also accepted.
    """
    text = icon_section.strip()
    if not text or text == "无":
        return set()
    icons: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        list_match = re.match(
            r"^[-*+]\s+`?([a-z0-9]+(?:-[a-z0-9]+)*)`?(?:\s|[（(,，]|$)",
            stripped,
        )
        if list_match:
            icons.add(list_match.group(1))
            continue
        if stripped.startswith(("-", "*", "+")):
            continue
        for token in re.split(r"[,，、\s]+", stripped):
            token = token.strip().strip("`")
            # Drop Chinese parenthetical notes glued to the name.
            token = re.split(r"[（(]", token, maxsplit=1)[0].strip()
            if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", token):
                icons.add(token)
    return icons


def validate_scoped_css(css: str, *, label: str) -> list[str]:
    """Reject CSS that would escape an @scope wrapper via unbalanced braces."""
    depth = 0
    index = 0
    length = len(css)
    while index < length:
        char = css[index]
        if char == "/" and index + 1 < length and css[index + 1] == "*":
            end = css.find("*/", index + 2)
            if end < 0:
                return [f"{label}：CSS 注释未闭合"]
            index = end + 2
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            while index < length:
                if css[index] == "\\":
                    index += 2
                    continue
                if css[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return [f"{label}：CSS 括号不配对，会跳出章节 @scope 作用域"]
        index += 1
    if depth != 0:
        return [f"{label}：CSS 括号不配对，会跳出章节 @scope 作用域"]
    return []


def validate_wiki(base: Path, cfg: dict[str, Any] | None = None) -> list[str]:
    wiki = base / "wiki"
    errors: list[str] = []
    index = wiki / "index.md"
    pages = list(wiki.rglob("*.md"))
    if not index.exists():
        errors.append("缺少 wiki/index.md")
    elif cfg:
        index_text = index.read_text(encoding="utf-8")
        headings = re.findall(r"^##\s+(.+?)\s*$", index_text, flags=re.MULTILINE)
        for chapter in cfg.get("chapters", []):
            if chapter not in headings:
                errors.append(f"wiki/index.md：缺少报告章节分组：{chapter}")
        indexed_pages = set()
        for link in markdown_links(index):
            resolved = resolve_local_markdown_path(link, index)
            if resolved is None:
                continue
            try:
                indexed_pages.add(resolved.relative_to(wiki.resolve()).as_posix())
            except ValueError:
                continue
        for page in pages:
            relative = page.relative_to(wiki).as_posix()
            if relative not in {"README.md", "index.md", "log.md"} and relative not in indexed_pages:
                errors.append(f"wiki/index.md：专题页面尚未加入索引：{relative}")
    for page in pages:
        for link in markdown_links(page):
            resolved = resolve_local_markdown_path(link, page)
            if resolved is not None and not resolved.exists():
                errors.append(f"{page.relative_to(wiki).as_posix()}：链接目标不存在：{link}")
    return errors


def validate_report(base: Path, cfg: dict[str, Any]) -> list[str]:
    folder = base / "reports"
    errors = []
    for chapter in cfg.get("chapters", []):
        path = folder / f"{slug(chapter)}.md"
        if not path.exists():
            errors.append(f"缺少报告章节：{path.name}")
            continue
        text = path.read_text(encoding="utf-8").strip()
        if len(text) < 30:
            errors.append(f"报告章节内容过短：{path.name}")
        for target in markdown_links(path):
            resolved = resolve_local_markdown_path(target, path)
            if resolved is not None and not resolved.exists():
                errors.append(f"{path.name}：引用目标不存在：{target}")
    return errors


def validate_spec(base: Path, cfg: dict[str, Any]) -> list[str]:
    folder = base / "specs"
    errors = []
    page_ids: set[str] = set()
    page_roles: list[str] = []
    for chapter in cfg.get("chapters", []):
        path = folder / f"{slug(chapter)}.md"
        if not path.exists():
            errors.append(f"缺少 Spec 章节：{path.name}")
            continue
        text = path.read_text(encoding="utf-8").strip()
        matches = list(re.finditer(r"^##\s+Slide\s+(\d+)\s+[—-].*$", text, flags=re.MULTILINE))
        if not matches:
            errors.append(f"未找到分页标题（格式：## Slide 1 — 标题）：{path.name}")
            continue
        required = ("目的", "核心结论", "展示内容", "证据与来源", "限定条件", "报告段落映射", "布局意图", "图标需求")
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            page = text[match.start():end]
            slide_number = match.group(1)
            page_id_match = re.search(r"^页面 ID\s*[：:]\s*(\S+)\s*$", page, flags=re.MULTILINE)
            if not page_id_match:
                errors.append(f"{path.name} Slide {slide_number}：缺少页面 ID")
            elif page_id_match.group(1) in page_ids:
                errors.append(f"{path.name} Slide {slide_number}：页面 ID 重复：{page_id_match.group(1)}")
            else:
                page_ids.add(page_id_match.group(1))
            role_match = re.search(r"^页面角色\s*[：:]\s*(cover|content)\s*$", page, flags=re.MULTILINE | re.IGNORECASE)
            if not role_match:
                errors.append(f"{path.name} Slide {slide_number}：页面角色必须填写 cover 或 content")
                page_roles.append("")
            else:
                page_roles.append(role_match.group(1).lower())
                if role_match.group(1).lower() == "cover" and re.search(r"```echarts-spec\s*\n", page):
                    errors.append(f"{path.name} Slide {slide_number}：cover 页面不能包含定量图表")
            for heading in required:
                if not re.search(rf"^###\s+{re.escape(heading)}\s*$", page, flags=re.MULTILINE):
                    errors.append(f"{path.name} Slide {slide_number}：缺少 ### {heading}")
            mapping = re.search(r"^###\s+报告段落映射\s*\n(.*?)(?=^###\s|\Z)", page, flags=re.MULTILINE | re.DOTALL)
            if mapping and not mapping.group(1).strip():
                errors.append(f"{path.name} Slide {slide_number}：报告段落映射不能为空")
            for raw in re.findall(r"```echarts-spec\s*\n(.*?)\n```", page, flags=re.DOTALL):
                try:
                    spec = json.loads(raw)
                    if not isinstance(spec, dict):
                        raise ValueError("图表规格必须是 JSON 对象")
                    validate_chart_spec(spec)
                    if not isinstance(spec.get("source"), str) or not spec["source"].strip():
                        raise ValueError("图表规格必须标注来源")
                    source = spec["source"]
                    if not re.match(r"^https?://", source, flags=re.I) and not (path.parent / source).resolve().exists():
                        raise ValueError(f"图表来源目标不存在：{source}")
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"{path.name} Slide {slide_number}：图表规格无效：{exc}")
        for target in markdown_links(path):
            resolved = resolve_local_markdown_path(target, path)
            if resolved is not None and not resolved.exists():
                errors.append(f"{path.name}：来源链接目标不存在：{target}")
    if page_roles:
        if page_roles[0] != "cover":
            errors.append("全套 Spec 的第一张页面必须是 cover")
        if page_roles.count("cover") != 1:
            errors.append("全套 Spec 必须且只能包含一个 cover 页面")
        if any(role not in {"cover", "content"} for role in page_roles):
            errors.append("Spec 页面角色无效")
    return errors


class SlideFragmentParser(HTMLParser):
    """Collect slide sections from one agent-produced chapter fragment."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    # Whitelist: presentation HTML + common SVG. Dangerous tags are rejected outright.
    ALLOWED_TAGS = frozenset({
        "section", "div", "span", "header", "footer", "main", "article", "aside", "nav",
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "dl", "dt", "dd",
        "a", "strong", "em", "b", "i", "u", "s", "small", "mark", "abbr", "time", "sub", "sup",
        "code", "pre", "blockquote", "q", "cite", "figure", "figcaption",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
        "img", "picture", "source",
        "svg", "g", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse",
        "text", "tspan", "defs", "use", "symbol", "clippath", "lineargradient", "radialgradient",
        "stop", "title", "desc", "mask", "pattern", "marker",
        "script", "style",
    })
    FORBIDDEN_TAGS = frozenset({
        "meta", "form", "animate", "set", "animatetransform", "animatemotion",
        "iframe", "object", "embed", "base", "link", "input", "button", "textarea", "select",
        "option", "applet", "frame", "frameset", "video", "audio", "portal", "foreignobject",
    })
    ALLOWED_ATTRS = frozenset({
        "id", "class", "lang", "dir", "title", "role", "tabindex", "hidden", "type",
        "href", "alt", "width", "height", "loading", "decoding", "colspan", "rowspan", "scope", "span",
        "viewbox", "xmlns", "xmlns:xlink", "fill", "stroke", "stroke-width", "stroke-linecap",
        "stroke-linejoin", "opacity", "transform", "d", "cx", "cy", "r", "rx", "ry",
        "x", "y", "x1", "y1", "x2", "y2", "points", "preserveaspectratio", "clip-path",
        "fill-rule", "clip-rule", "font-size", "font-family", "font-weight", "text-anchor",
        "dominant-baseline", "gradientunits", "gradienttransform", "offset", "stop-color",
        "stop-opacity", "xlink:href", "href", "aria-hidden", "aria-label", "aria-labelledby",
        "focusable", "overflow", "vector-effect", "style",
    })
    URL_ATTRS = frozenset({
        "href", "action", "formaction", "xlink:href", "poster", "background", "to", "values", "from",
    })
    SRC_ATTRS = frozenset({"src", "srcset"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.slides: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.css: list[str] = []
        self.active: dict[str, Any] | None = None
        self.stack: list[str] = []
        self.style = False
        self.note_script = False
        self.asset_script: str | None = None
        self.asset_data: list[str] = []
        self._skip_depth = 0

    @staticmethod
    def render_tag(tag: str, attrs: list[tuple[str, str | None]], closed: bool = False) -> str:
        rendered = "".join(f' {name}="{html.escape(value or "", quote=True)}"' for name, value in attrs)
        return f"<{tag}{rendered}{' /' if closed else ''}>"

    @staticmethod
    def normalize_url_candidate(value: str) -> str:
        """Decode entities, strip whitespace/controls, lowercase — for protocol checks."""
        decoded = html.unescape(value or "")
        return re.sub(r"[\s\x00-\x1f\x7f]+", "", decoded).lower()

    @classmethod
    def is_allowed_url(cls, value: str) -> bool:
        normalized = cls.normalize_url_candidate(value)
        if not normalized:
            return True
        if normalized.startswith("#"):
            return True
        if normalized.startswith("//"):
            return False
        if normalized.startswith("https:") or normalized.startswith("mailto:"):
            return True
        # Block any other scheme (javascript:, data:, http:, vbscript:, …).
        if re.match(r"^[a-z][a-z0-9+.-]*:", normalized):
            return False
        return True

    def sanitize_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        cleaned: list[tuple[str, str | None]] = []
        for name, value in attrs:
            lower = name.lower()
            if lower.startswith("on"):
                self.errors.append(f"章节片段不允许内联事件属性：{name}")
                continue
            if lower.startswith("data-") or lower.startswith("aria-"):
                cleaned.append((name, value))
                continue
            if lower in self.SRC_ATTRS:
                if value and not value.strip().lower().startswith("data:"):
                    self.errors.append(f"章节片段包含外部资源：{value}")
                    continue
                cleaned.append((name, value))
                continue
            if lower in self.URL_ATTRS:
                if value and not self.is_allowed_url(value):
                    self.errors.append(f"章节片段包含不安全链接属性 {name}：{value}")
                    continue
                cleaned.append((name, value))
                continue
            if lower == "style" and value and re.search(r"url\s*\(|@import", value, flags=re.I):
                self.errors.append("章节片段的 style 属性包含外部导入或 URL")
                continue
            if lower not in self.ALLOWED_ATTRS:
                self.errors.append(f"章节片段不允许属性：{name}")
                continue
            cleaned.append((name, value))
        return cleaned

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            if lower_tag not in self.VOID:
                self._skip_depth += 1
            return
        attr = {name: value for name, value in attrs}
        classes = (attr.get("class") or "").split()
        if lower_tag in self.FORBIDDEN_TAGS or lower_tag not in self.ALLOWED_TAGS:
            self.errors.append(f"章节片段不允许使用 <{tag}>")
            if lower_tag not in self.VOID:
                self._skip_depth = 1
            return
        if lower_tag == "script":
            allowed = {"slide-notes", "mls-echarts-spec", "mls-lucide-spec"}
            if attr.get("type") != "application/json" or not (allowed & set(classes)):
                self.errors.append("章节片段包含脚本；只允许 slide-notes、mls-echarts-spec 或 mls-lucide-spec JSON 标记")
                self._skip_depth = 1
                return
            if "slide-notes" in classes:
                if self.active and self.active["has_notes"]:
                    self.errors.append("每张 slide 只能包含一个 slide-notes 对象")
                if self.active:
                    self.active["has_notes"] = True
                self.note_script = True
            asset_classes = {"mls-echarts-spec", "mls-lucide-spec"} & set(classes)
            if asset_classes:
                if len(asset_classes) != 1:
                    self.errors.append("每个渲染标记只能使用一种资产类型")
                if not self.active:
                    self.errors.append("ECharts/Lucide 标记必须位于 slide 内")
                self.asset_script = next(iter(asset_classes))
                self.asset_data = []
        safe_attrs = self.sanitize_attrs(lower_tag, attrs)
        if lower_tag == "style":
            self.style = True
        is_slide = "slide" in classes
        if is_slide:
            if self.active:
                self.errors.append("章节片段中不允许嵌套 slide")
            else:
                if lower_tag not in {"section", "div"}:
                    self.errors.append("slide 根元素必须是 <section> 或 <div>")
                slide_id = attr.get("id", "") or ""
                self.active = {"html": [], "notes": [], "assets": [], "has_notes": False, "id": slide_id,
                               "role": attr.get("data-page-role", "") or ""}
                self.stack = []
        if self.active:
            self.active["html"].append(self.render_tag(tag, safe_attrs))
            if lower_tag not in self.VOID:
                self.stack.append(lower_tag)
        if lower_tag in self.VOID and self.active and is_slide:
            self.errors.append("slide 根元素必须是 section 或 div")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            return
        if lower_tag in self.FORBIDDEN_TAGS or lower_tag not in self.ALLOWED_TAGS:
            self.errors.append(f"章节片段不允许使用 <{tag}>")
            return
        safe_attrs = self.sanitize_attrs(lower_tag, attrs)
        rendered = self.render_tag(tag, safe_attrs, closed=True)
        if self.active:
            self.active["html"].append(rendered)
        elif lower_tag == "style":
            self.errors.append("style 元素不能为空")

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            if lower_tag not in self.VOID:
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        if lower_tag == "style":
            self.style = False
        if lower_tag == "script":
            self.note_script = False
            if self.asset_script:
                try:
                    spec = json.loads("".join(self.asset_data))
                    if not isinstance(spec, dict):
                        raise ValueError("JSON 必须是对象")
                    kind = "chart" if self.asset_script == "mls-echarts-spec" else "icon"
                    if self.active:
                        self.active["assets"].append({"kind": kind, "spec": spec})
                except (json.JSONDecodeError, ValueError) as exc:
                    self.errors.append(f"{self.asset_script} JSON 无效：{exc}")
                self.asset_script = None
                self.asset_data = []
        if self.active:
            self.active["html"].append(f"</{tag}>")
            if self.stack and self.stack[-1] == lower_tag:
                self.stack.pop()
            elif lower_tag in self.stack:
                self.errors.append(f"HTML 标签嵌套顺序错误：</{tag}>")
                self.stack = self.stack[:self.stack.index(lower_tag)]
            if not self.stack:
                slide = self.active
                self.slides.append(slide)
                self.active = None
                self.note_script = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self.style:
            self.css.append(data)
        if self.active:
            self.active["html"].append(data)
            if self.note_script:
                self.active["notes"].append(data)
            if self.asset_script:
                self.asset_data.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth:
            return
        raw = f"&{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_charref(self, name: str) -> None:
        if self._skip_depth:
            return
        raw = f"&#{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_comment(self, data: str) -> None:
        if self._skip_depth:
            return
        if self.active:
            self.active["html"].append(f"<!--{data}-->")


def build_slides(base: Path, cfg: dict[str, Any], *, write: bool = True) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    all_slides: list[tuple[str, dict[str, Any]]] = []
    assets_to_render: list[dict[str, Any]] = []
    approved_chart_specs: set[str] = set()
    approved_icons: set[str] = set()
    expected_page_roles: list[str] = []
    for chapter in cfg.get("chapters", []):
        spec_path = base / "specs" / f"{slug(chapter)}.md"
        if not spec_path.exists():
            continue
        spec_text = spec_path.read_text(encoding="utf-8")
        for page in re.split(r"(?=^##\s+Slide\s+\d+\s+[—-])", spec_text, flags=re.MULTILINE)[1:]:
            role_match = re.search(r"^页面角色\s*[：:]\s*(cover|content)\s*$", page, flags=re.MULTILINE | re.IGNORECASE)
            if role_match:
                expected_page_roles.append(role_match.group(1).lower())
        for raw_spec in re.findall(r"```echarts-spec\s*\n(.*?)\n```", spec_text, flags=re.DOTALL):
            try:
                chart_spec = json.loads(raw_spec)
                approved_chart_specs.add(json.dumps(chart_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            except json.JSONDecodeError:
                pass
        for icon_section in re.findall(r"^###\s+图标需求\s*$\s*(.*?)(?=^###\s|^##\s|\Z)", spec_text, flags=re.MULTILINE | re.DOTALL):
            approved_icons.update(extract_approved_icons(icon_section))
    css_blocks: list[str] = []
    seen_ids: set[str] = set()
    for chapter in cfg.get("chapters", []):
        path = base / "slides" / "chapters" / f"{slug(chapter)}.html"
        if not path.exists():
            errors.append(f"缺少 Slides 章节：{path.relative_to(base).as_posix()}")
            continue
        parser = SlideFragmentParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except Exception as exc:
            errors.append(f"{path.name}：HTML 解析失败：{exc}")
            continue
        errors.extend(f"{path.name}：{issue}" for issue in parser.errors)
        if parser.active:
            errors.append(f"{path.name}：slide 标签未闭合")
        if not parser.slides:
            errors.append(f"{path.name}：没有 class=\"slide\" 的页面")
        css = "".join(parser.css)
        if re.search(r"@import|url\s*\(", css, flags=re.I):
            errors.append(f"{path.name}：样式包含外部导入或 URL")
        errors.extend(validate_scoped_css(css, label=path.name))
        css_blocks.append(f'@scope ([data-chapter="{slug(chapter)}"]) {{\n{css}\n}}')
        for slide in parser.slides:
            if not slide["has_notes"]:
                errors.append(f"{path.name}：每张 slide 都需要一个 slide-notes JSON 对象")
            else:
                try:
                    note = json.loads("".join(slide["notes"]))
                    if not isinstance(note, dict):
                        errors.append(f"{path.name}：slide-notes 必须是 JSON 对象")
                    elif (not isinstance(note.get("title"), str) or not note["title"].strip()
                          or not isinstance(note.get("script"), str) or not note["script"].strip()
                          or not isinstance(note.get("notes"), list)
                          or any(not isinstance(item, str) for item in note.get("notes", []))):
                        errors.append(f"{path.name}：slide-notes 必须包含 title、script 和字符串数组 notes")
                except json.JSONDecodeError:
                    errors.append(f"{path.name}：slide-notes JSON 无效")
            for asset in slide["assets"]:
                try:
                    if asset["kind"] == "chart":
                        validate_chart_spec(asset["spec"])
                        canonical = json.dumps(asset["spec"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        if canonical not in approved_chart_specs:
                            raise ValueError("图表数据必须与已批准 Spec 中的 echarts-spec 完全一致")
                    else:
                        icon_name = asset["spec"].get("name", "")
                        if not isinstance(icon_name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", icon_name):
                            raise ValueError("Lucide 图标名称必须使用 kebab-case")
                        if icon_name not in approved_icons:
                            raise ValueError(f"图标 {icon_name} 未在已批准 Spec 的图标需求中声明")
                    asset["id"] = f"asset-{len(assets_to_render)}"
                    assets_to_render.append(asset)
                except ValueError as exc:
                    errors.append(f"{path.name}：标记校验失败：{exc}")
            for found in re.findall(r'\bid=["\']([^"\']+)["\']', "".join(slide["html"])):
                if found in seen_ids:
                    errors.append(f"重复的 HTML id：{found}")
                seen_ids.add(found)
            all_slides.append((chapter, slide))
    if errors:
        return None, errors
    if not all_slides:
        return None, ["没有可合并的 slide"]
    actual_page_roles = [slide["role"] for _, slide in all_slides]
    if expected_page_roles and actual_page_roles != expected_page_roles:
        return None, ["HTML Slides 的页面角色或顺序必须与已批准 Spec 完全一致"]
    if expected_page_roles and actual_page_roles and (actual_page_roles[0] != "cover" or actual_page_roles.count("cover") != 1):
        return None, ["整套 HTML Slides 必须以唯一的 cover 页面开场"]
    try:
        brand_color = cfg.get("brand_color", "#A6192E")
        if not isinstance(brand_color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
            return None, ["project.yaml 的 brand_color 必须是 #RRGGBB 格式"]
        rendered_assets = render_assets(assets_to_render, brand_color)
    except (OSError, ValueError) as exc:
        return None, [str(exc)]
    sections = []
    for number, (chapter, slide) in enumerate(all_slides):
        source = "".join(slide["html"])
        asset_index = 0
        # Match complete class tokens only — avoid substring hits like old-mls-lucide-spec.
        marker_pattern = re.compile(
            r'<script\b(?=[^>]*\btype="application/json")'
            r'(?=[^>]*\bclass="(?:[^"]*\s)?(?:mls-echarts-spec|mls-lucide-spec)(?:\s[^"]*)?")'
            r"[^>]*>.*?</script>",
            flags=re.DOTALL,
        )
        def replace_asset(_match: re.Match[str]) -> str:
            nonlocal asset_index
            asset = slide["assets"][asset_index]
            asset_index += 1
            return rendered_assets[asset["id"]]
        source = marker_pattern.sub(replace_asset, source)
        if asset_index != len(slide["assets"]):
            return None, [f"{chapter}：Slides 渲染标记解析数量不一致"]
        source = re.sub(r'\sdata-slide=["\'][^"\']*["\']', "", source, count=1)
        marker = f'data-slide="{number}" data-chapter="{html.escape(slug(chapter), quote=True)}"'

        def rewrite_root_slide_class(match: re.Match[str]) -> str:
            # Only the slide root class list — never rewrite body text like "active".
            classes = [token for token in match.group(1).split() if token != "active"]
            if not number:
                classes.append("active")
            return f'class="{" ".join(classes)}" {marker}'

        source = re.sub(
            r'\bclass=["\']([^"\']*\bslide\b[^"\']*)["\']',
            rewrite_root_slide_class,
            source,
            count=1,
        )
        sections.append(source)
    title = cfg.get("project", "Investment presentation")
    brand_color = cfg.get("brand_color", "#A6192E")
    renderer_meta = "ECharts 6.1.0 (Apache-2.0); Lucide Static 1.52.0 (ISC)" if assets_to_render else "Native HTML/CSS only"
    design_meta = "bluedusk/html-slides@d8289f4c317905cc5d0ca265d32b791e6cb387b7 (MIT)"
    notices = ""
    if assets_to_render:
        notices = '<details id="third-party-notices"><summary>第三方许可与来源</summary>' + renderer_notices() + "</details>"
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="my-slides"><meta name="my-slides-renderers" content="{html.escape(renderer_meta, quote=True)}"><meta name="design-reference" content="{html.escape(design_meta, quote=True)}"><title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:#ececee;color:#20232a;font-family:Inter,"Microsoft YaHei",sans-serif}}
body{{display:grid;place-items:center;min-height:100vh}}#deckStage{{width:min(100vw,177.7778vh);aspect-ratio:16/9;background:#f9f8f5;box-shadow:0 12px 48px #1113;position:relative;overflow:hidden}}
#deck{{position:absolute;inset:0}}.slide{{position:absolute;left:0;top:0;width:1920px;height:1080px;padding:5.5%;overflow:hidden;display:none;background:#f9f8f5;transform-origin:top left}}.slide.active{{display:block}}
.slide svg{{display:block;max-width:100%;max-height:58%;width:auto;height:auto;margin-inline:auto}}
button{{font:inherit;border:0;border-radius:6px;padding:.6em 1em;background:{brand_color};color:#fff;cursor:pointer}}#controls{{position:fixed;bottom:16px;display:flex;gap:12px;align-items:center;color:#333}}
#third-party-notices{{position:fixed;right:12px;top:12px;z-index:1000;max-width:min(560px,90vw);max-height:80vh;overflow:auto;background:#fff;border:1px solid #d4d4d8;border-radius:8px;padding:8px 12px;box-shadow:0 4px 20px #0002}}#third-party-notices pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}
@media print{{body{{display:block;background:white}}#deckStage{{width:100%;height:auto;box-shadow:none;overflow:visible}}.slide{{position:relative;display:block;page-break-after:always;width:1920px!important;height:1080px!important;zoom:1!important}}#controls{{display:none}}}}
{''.join(css_blocks)}
</style></head><body><main id="deckStage" class="deck-stage" data-deck-stage><div id="deck" class="deck">{''.join(sections)}</div></main>
<nav id="controls" aria-label="Slides navigation"><button type="button" onclick="prev()">上一页</button><span id="pageCount"></span><button type="button" onclick="next()">下一页</button></nav>
{notices}
<script>
const pages=Array.from(document.querySelectorAll(".slide"));let current=0;
function fitSlides(){{const stage=document.getElementById("deckStage");const scale=Math.min(stage.clientWidth/1920,stage.clientHeight/1080);pages.forEach(p=>{{p.style.setProperty("width","1920px","important");p.style.setProperty("height","1080px","important");p.style.setProperty("zoom",String(scale),"important")}})}}
function goTo(n){{current=Math.max(0,Math.min(pages.length-1,n));pages.forEach((p,i)=>p.classList.toggle("active",i===current));document.getElementById("pageCount").textContent=(current+1)+" / "+pages.length}}
function next(){{goTo(current+1)}}function prev(){{goTo(current-1)}}
window.addEventListener("resize",fitSlides);fitSlides();
document.addEventListener("keydown",e=>{{if(["ArrowRight","PageDown"," "].includes(e.key))next();if(["ArrowLeft","PageUp"].includes(e.key))prev()}});
let touchX=0;document.getElementById("deckStage").addEventListener("touchstart",e=>touchX=e.changedTouches[0].clientX,{{passive:true}});
document.getElementById("deckStage").addEventListener("touchend",e=>{{const delta=e.changedTouches[0].clientX-touchX;if(Math.abs(delta)>50)(delta<0?next:prev)()}},{{passive:true}});goTo(0);
</script></body></html>
"""
    output = base / "slides" / "index.html"
    if write:
        generated_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
        if output.exists():
            previous = output.read_bytes()
            previous_hash = hashlib.sha256(previous).hexdigest()
            if previous_hash != generated_hash:
                archive = base / ".state" / "deliveries" / f"{previous_hash}.html"
                archive.parent.mkdir(parents=True, exist_ok=True)
                if not archive.exists():
                    archive.write_bytes(previous)
        output.write_bytes(document.encode("utf-8"))
        approvals_path = base / ".state" / "approvals.json"
        approvals = json.loads(approvals_path.read_text(encoding="utf-8")) if approvals_path.exists() else {}
        state = {
            "built_at": now(),
            "html_sha256": generated_hash,
            "report_sha256": approvals.get("report", {}).get("sha256"),
            "spec_sha256": approvals.get("spec", {}).get("sha256"),
        }
        state_path = base / ".state" / "slides.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output, []


def approval_digest(base: Path, kind: str, cfg: dict[str, Any]) -> str | None:
    folder = base / ("reports" if kind == "report" else "specs")
    paths = [folder / f"{slug(chapter)}.md" for chapter in cfg.get("chapters", [])]
    if not paths or any(not path.exists() for path in paths):
        return None
    payload = "\n".join(hashlib.sha256(path.read_bytes()).hexdigest() for path in paths)
    return hashlib.sha256(payload.encode()).hexdigest()


def approval_is_current(base: Path, kind: str, cfg: dict[str, Any]) -> bool:
    path = base / ".state" / "approvals.json"
    if not path.exists():
        return False
    approvals = json.loads(path.read_text(encoding="utf-8"))
    current = approval_digest(base, kind, cfg)
    item = approvals.get(kind, {})
    if current is None or item.get("sha256") != current:
        return False
    if kind == "spec":
        return approval_is_current(base, "report", cfg) and item.get("report_sha256") == approvals.get("report", {}).get("sha256")
    if item.get("source_sha256") != source_digest(base.parent, cfg):
        return False
    return True


def slides_is_current(base: Path, cfg: dict[str, Any]) -> bool:
    state_path = base / ".state" / "slides.json"
    output = base / "slides" / "index.html"
    if not state_path.exists() or not output.exists():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return (
        state.get("html_sha256") == hashlib.sha256(output.read_bytes()).hexdigest()
        and state.get("report_sha256") == approval_digest(base, "report", cfg)
        and state.get("spec_sha256") == approval_digest(base, "spec", cfg)
        and approval_is_current(base, "report", cfg)
        and approval_is_current(base, "spec", cfg)
    )


def renderer_home() -> Path:
    override = os.environ.get("MY_SLIDES_RENDERER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "MySlides" / "renderer"
    return Path.home() / ".local" / "share" / "my-slides" / "renderer"


def renderer_status() -> dict[str, Any]:
    node = shutil.which("node")
    npm = shutil.which("npm")
    home = renderer_home()
    packages: dict[str, str | None] = {}
    for package in ("echarts", "lucide-static"):
        metadata = home / "node_modules" / package / "package.json"
        if metadata.exists():
            packages[package] = json.loads(metadata.read_text(encoding="utf-8")).get("version")
        else:
            packages[package] = None
    return {"node": node, "npm": npm, "home": str(home), "packages": packages,
            "ready": bool(node and npm and packages == {"echarts": "6.1.0", "lucide-static": "1.52.0"})}


def install_renderers() -> dict[str, Any]:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise ValueError("安装图表和图标渲染器需要 Node.js 与 npm；安装 Node.js 后重试 my-slides renderer install")
    existing = renderer_status()
    if existing["ready"]:
        return existing
    home = renderer_home()
    resources = Path(__file__).parent / "renderer"
    home.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        source = resources / name
        if not source.exists():
            raise ValueError(f"安装包缺少渲染依赖清单：{source.name}")
        (home / name).write_bytes(source.read_bytes())
    cache = home / ".npm-cache"
    result = subprocess.run([npm, "ci", "--prefix", str(home), "--cache", str(cache), "--ignore-scripts", "--no-audit", "--no-fund"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError("npm 安装渲染依赖失败：" + (result.stderr or result.stdout).strip())
    status = renderer_status()
    if not status["ready"]:
        raise ValueError(f"渲染器版本不符合锁定要求：{status['packages']}")
    return status


def _is_js_parseable_date(value: str) -> bool:
    """Approximate JS Date.parse for the ISO / common forms used in charts."""
    text = value.strip()
    if not text:
        return False
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            datetime.fromisoformat(candidate)
            return True
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def validate_chart_spec(spec: dict[str, Any]) -> None:
    kind = spec.get("type")
    supported = {"bar", "dot", "line", "multi-line", "scatter", "time-scatter", "stacked-bar", "waterfall"}
    if kind not in supported:
        raise ValueError(f"不支持的图表类型：{kind}")
    def values_ok(values: Any, label: str) -> None:
        if not isinstance(values, list) or not values:
            raise ValueError(f"{label} 必须是非空数组")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not __import__("math").isfinite(value) for value in values):
            raise ValueError(f"{label} 必须全部为有限数值；缺失值不能按 0 绘制")
    width = spec.get("width")
    height = spec.get("height")
    effective_width = width if isinstance(width, int) and not isinstance(width, bool) else 1100
    effective_height = height if isinstance(height, int) and not isinstance(height, bool) else 560
    if effective_width < 320 or effective_width > 1800 or effective_height < 240 or effective_height > 1000:
        raise ValueError("图表宽高超出允许范围（宽 320–1800，高 240–1000）")
    if kind in {"bar", "dot", "line", "waterfall"}:
        categories = spec.get("categories")
        if not isinstance(categories, list) or not categories or any(not isinstance(v, str) or not v.strip() for v in categories):
            raise ValueError("categories 必须是非空文本数组")
        values_ok(spec.get("values"), "values")
        if len(categories) != len(spec["values"]):
            raise ValueError("categories 与 values 长度必须一致")
    if kind in {"multi-line", "stacked-bar"}:
        categories, series = spec.get("categories"), spec.get("series")
        if not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
            raise ValueError("categories 和 series 必须为非空数组")
        unit = spec.get("unit", "")
        for item in series:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError("每个 series 都必须有名称")
            values_ok(item.get("values"), f"series {item.get('name')}")
            if len(item["values"]) != len(categories):
                raise ValueError(f"series {item['name']} 与 categories 长度不一致")
            if item.get("unit", unit) != unit:
                raise ValueError(f"series {item['name']} 单位与图表单位不一致")
    if kind in {"scatter", "time-scatter"}:
        points = spec.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError("points 必须为非空数组")
        if not isinstance(spec.get("xUnit"), str) or not isinstance(spec.get("yUnit"), str):
            raise ValueError("散点图必须分别明确 xUnit 和 yUnit")
        for point in points:
            if not isinstance(point, dict):
                raise ValueError("散点数据必须为对象数组")
            if kind == "scatter":
                values_ok([point.get("x"), point.get("y")], "散点坐标")
            else:
                date = point.get("date")
                y_value = point.get("y")
                if (
                    not isinstance(date, str)
                    or not _is_js_parseable_date(date)
                    or isinstance(y_value, bool)
                    or not isinstance(y_value, (int, float))
                    or not __import__("math").isfinite(y_value)
                ):
                    raise ValueError("时间散点需要可解析的 date 和有限数值 y")
    if kind == "waterfall":
        totals = spec.get("totals", [])
        if not isinstance(totals, list) or any(not isinstance(i, int) or i < 0 or i >= len(spec["values"]) for i in totals):
            raise ValueError("waterfall totals 必须为有效的数据索引")


def sanitize_svg(svg: str, name: str) -> str:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"{name} 渲染结果不是有效 SVG：{exc}") from exc
    allowed = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs", "clipPath", "linearGradient", "radialGradient", "stop", "pattern", "mask", "filter", "feGaussianBlur", "feOffset", "feBlend", "title", "desc", "style"}
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag not in allowed:
            raise ValueError(f"{name} SVG 包含不允许的元素：{tag}")
        if tag == "style" and re.search(r"@import|url\s*\(\s*['\"]?(?!#)", element.text or "", flags=re.I):
            raise ValueError(f"{name} SVG 样式包含外部导入或 URL")
        for key, value in element.attrib.items():
            attr = key.split("}")[-1].lower()
            if attr.startswith("on") or (attr in {"href", "src"} and not value.startswith("#")):
                raise ValueError(f"{name} SVG 包含不安全属性：{attr}")
            if "javascript:" in value.lower() or "@import" in value.lower():
                raise ValueError(f"{name} SVG 包含不安全内容")
            if attr == "style" and re.search(r"url\s*\(\s*['\"]?(?!#)", value, flags=re.I):
                raise ValueError(f"{name} SVG 样式包含外部 URL")
    return svg


def render_assets(assets: list[dict[str, Any]], brand_color: str = "#A6192E") -> dict[str, str]:
    if not assets:
        return {}
    status = renderer_status()
    if not status["ready"]:
        raise ValueError("本地渲染器未就绪，请运行 my-slides renderer install；状态：" + json.dumps(status, ensure_ascii=False))
    script = Path(__file__).parent / "renderer" / "render.mjs"
    env = os.environ.copy()
    env["MY_SLIDES_RENDERER_HOME"] = str(renderer_home())
    result = subprocess.run([status["node"], str(script)], input=json.dumps({"assets": assets, "brandColor": brand_color}, ensure_ascii=False),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if result.returncode:
        raise ValueError("本地 SVG 渲染失败：" + (result.stderr or result.stdout).strip())
    try:
        rendered = json.loads(result.stdout).get("rendered", {})
    except json.JSONDecodeError as exc:
        raise ValueError("本地渲染器返回了无效结果") from exc
    if set(rendered) != {asset["id"] for asset in assets}:
        raise ValueError("本地渲染器返回结果不完整")
    return {key: sanitize_svg(value, key) for key, value in rendered.items()}


def renderer_notices() -> str:
    home = renderer_home() / "node_modules"
    notices = []
    for package, version, license_name, source in (
        ("echarts", "6.1.0", "Apache-2.0", "https://github.com/apache/echarts"),
        ("lucide-static", "1.52.0", "ISC", "https://github.com/lucide-icons/lucide"),
    ):
        text = (home / package / "LICENSE").read_text(encoding="utf-8")
        notices.append(f"<h3>{html.escape(package)} {version} · {license_name}</h3><p><a href=\"{source}\">{source}</a></p><pre>{html.escape(text)}</pre>")
    return "\n".join(notices)


def browser_status() -> dict[str, Any]:
    installed = importlib.util.find_spec("playwright") is not None
    chromium = None
    if installed:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                chromium = playwright.chromium.executable_path
        except Exception:
            chromium = None
    return {"playwright": installed, "chromium": chromium, "chromium_installed": bool(chromium and Path(chromium).exists())}


def install_browser() -> dict[str, Any]:
    status = browser_status()
    if not status["playwright"]:
        raise ValueError("Playwright 未安装；请使用 uv tool install --editable '.[browser]' 安装 browser extra")
    result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError("Chromium 安装失败：" + (result.stderr or result.stdout).strip())
    status = browser_status()
    if not status["chromium_installed"]:
        raise ValueError("Playwright 安装完成，但未找到 Chromium 可执行文件")
    return status


def approve_revision(base: Path, cfg: dict[str, Any], kind: str) -> tuple[str | None, list[str]]:
    if detect_format_version(base) == "v2":
        return None, [
            "当前项目为 v2 单元格式，暂不支持章节级 approve；"
            "旧章节批准结果不可用于单元工作流"
        ]
    errors = validate_report(base, cfg) if kind == "report" else validate_spec(base, cfg)
    if kind == "report":
        _, pending, removed = scan_sources(base.parent, base, cfg)
        if pending or removed:
            errors.append("报告审阅前仍有未整理或已移除资料：" + "、".join(pending + removed))
    if kind == "spec" and not approval_is_current(base, "report", cfg):
        errors.append("请先审阅当前报告并运行 my-slides approve report")
    if errors:
        return None, errors
    digest = approval_digest(base, kind, cfg)
    if digest is None:
        return None, [f"{kind} 章节文件不完整"]
    approvals_path = base / ".state" / "approvals.json"
    approvals = json.loads(approvals_path.read_text(encoding="utf-8")) if approvals_path.exists() else {}
    revision_path = snapshot_approved_revision(base, cfg, kind, digest)
    approvals[kind] = {"sha256": digest, "approved_at": now(), "snapshot": revision_path.relative_to(base).as_posix()}
    if kind == "report":
        approvals[kind]["source_sha256"] = source_digest(base.parent, cfg)
    if kind == "spec":
        approvals[kind]["report_sha256"] = approvals["report"]["sha256"]
    approvals_path.write_text(json.dumps(approvals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return digest, []


def emit(args: argparse.Namespace, data: dict[str, Any], human: str, error: bool = False) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(human, file=sys.stderr if error else sys.stdout)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="my-slides", description="投资项目 Wiki、报告与 HTML Slides 本地工作流")
    parser.add_argument("--version", action="version", version="my-slides 0.2.0")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="初始化 v2 单元格式投资项目工作区")
    init.add_argument("--project", help="项目目录，默认当前目录")
    init.add_argument("--source-dir", action="append", help="资料目录（相对项目目录，可重复指定）")
    init.add_argument("--force", action="store_true", help="补全基础文件并重写项目配置")
    init.add_argument("--json", action="store_true")
    sources = sub.add_parser("sources", help="扫描或确认资料")
    source_sub = sources.add_subparsers(dest="sources_command", required=True)
    for name, help_text in (("scan", "扫描 Markdown 变化"), ("mark-ingested", "确认 agent 已整理当前变更资料")):
        command = source_sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        if name == "mark-ingested":
            command.add_argument("paths", nargs="*", help="项目相对路径；省略时确认所有待整理资料")
    def add_unit_selectors(command: argparse.ArgumentParser) -> None:
        command.add_argument("--unit", action="append", dest="units", metavar="ID", help="v2 单元 ID（可重复）")
        command.add_argument("--changed", action="store_true", help="v2：仅处理状态显示受影响/阻塞的单元")
        command.add_argument("--all", dest="all_units", action="store_true", help="v2：处理全部单元")

    prep = sub.add_parser("prepare", help="生成 agent 阶段交接材料")
    prep.add_argument("kind", choices=("wiki", "report", "spec", "slides"))
    prep.add_argument("--project")
    prep.add_argument("--json", action="store_true")
    prep.add_argument("--question", help="针对项目 Wiki 提出问题；省略时准备资料整理任务")
    add_unit_selectors(prep)
    validate = sub.add_parser("validate", help="检查 Wiki、报告或 Spec")
    validate.add_argument("kind", choices=("wiki", "report", "spec"))
    validate.add_argument("--project")
    validate.add_argument("--json", action="store_true")
    add_unit_selectors(validate)
    approve = sub.add_parser("approve", help="记录报告或 Spec 的用户批准版本")
    approve.add_argument("kind", choices=("report", "spec"))
    approve.add_argument("--project")
    approve.add_argument("--json", action="store_true")
    add_unit_selectors(approve)
    assemble = sub.add_parser("assemble", help="v2：将报告单元组装为 reports/report.md")
    assemble.add_argument("--project")
    assemble.add_argument("--json", action="store_true")
    renderer = sub.add_parser("renderer", help="检查或安装 ECharts 与 Lucide 本地渲染器")
    renderer_sub = renderer.add_subparsers(dest="renderer_command", required=True)
    for name, help_text in (("doctor", "检查 Node.js、npm 与锁定的渲染器版本"), ("install", "安装锁定版本的本地渲染依赖")):
        command = renderer_sub.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")
    browser = sub.add_parser("browser", help="检查或安装离线 Slides 浏览器验证环境")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    for name, help_text in (("doctor", "检查 Playwright 与 Chromium"), ("install", "安装 Playwright Chromium")):
        command = browser_sub.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")
    agent = sub.add_parser("agent", help="安装或检查 agent 工作流指引")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_install = agent_sub.add_parser("install", help="安装项目级工作流技能，不覆盖现有文件")
    agent_install.add_argument("--project", help="项目目录，默认当前目录")
    agent_install.add_argument("--json", action="store_true")
    slides = sub.add_parser("slides", help="合并并检查 HTML Slides")
    slides_sub = slides.add_subparsers(dest="slides_command", required=True)
    for name, help_text in (("build", "合并各章 HTML 片段 / v2 增量构建"), ("check", "检查章节 HTML 和合并文件")):
        command = slides_sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        command.add_argument("--browser", action="store_true", help="用桌面与手机视口运行 Chromium 验证")
        add_unit_selectors(command)
    units = sub.add_parser("units", help="查看 v2 内容单元清单")
    units_sub = units.add_subparsers(dest="units_command", required=True)
    units_list = units_sub.add_parser("list", help="列出单元身份、章节与产物是否齐全")
    units_list.add_argument("--project")
    units_list.add_argument("--json", action="store_true")
    migrate = sub.add_parser("migrate", help="项目格式迁移（预检 / 正式迁移 / 回滚）")
    migrate.add_argument("--to-units", action="store_true", help="预检或执行章节格式到单元格式的迁移")
    migrate.add_argument("--dry-run", action="store_true", help="只读扫描，不改写项目文件")
    migrate.add_argument("--rollback", action="store_true", help="回滚最近一次正式迁移备份")
    migrate.add_argument("--stamp", help="回滚指定备份时间戳（默认最新）")
    migrate.add_argument("--project")
    migrate.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor", help="检查项目工作区基础结构")
    doctor.add_argument("--project")
    doctor.add_argument("--json", action="store_true")
    status = sub.add_parser("status", help="查看项目阶段、待整理资料与单元状态")
    status.add_argument("--project")
    status.add_argument("--json", action="store_true")
    status.add_argument(
        "--unit",
        action="append",
        dest="units",
        metavar="ID",
        help="v2：查看指定单元状态（可重复）；省略则列出全部单元骨架",
    )
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            code = init_project(args)
        elif args.command == "renderer":
            status = install_renderers() if args.renderer_command == "install" else renderer_status()
            emit(args, status, json.dumps(status, ensure_ascii=False, indent=2), error=not status["ready"])
            code = 0 if status["ready"] else 1
        elif args.command == "browser":
            status = install_browser() if args.browser_command == "install" else browser_status()
            ok = status["playwright"] and status["chromium_installed"]
            emit(args, status, json.dumps(status, ensure_ascii=False, indent=2), error=not ok)
            code = 0 if ok else 1
        elif args.command == "agent":
            root = project_root(args.project, discover=False)
            result = install_agent_workflow(root)
            emit(args, result,
                 "已安装：" + (", ".join(result["installed"]) or "无") +
                 ("；已保留现有文件：" + ", ".join(result["preserved"]) if result["preserved"] else ""))
            code = 0
        else:
            root = project_root(args.project)
            base, cfg = ensure_project(root)
            format_version = detect_format_version(base)
            if args.command == "prepare":
                if args.kind == "wiki":
                    require_v2_project(base)
                else:
                    refuse_unsupported_v2_action(base, f"prepare {args.kind}", unit_mode=v2_unit_mode(args))
                code = prepare(args)
            elif args.command == "sources":
                require_v2_project(base)
                state, pending, removed = scan_sources(root, base, cfg)
                if args.sources_command == "mark-ingested":
                    selected = args.paths or (pending + removed)
                    unknown = sorted(set(selected) - set(state["files"]))
                    if unknown:
                        raise ValueError("资料路径未出现在扫描结果中：" + "、".join(unknown))
                    wiki_errors = validate_wiki(base, cfg)
                    if wiki_errors:
                        raise ValueError("Wiki 链接检查未通过，暂不能确认整理完成：" + "；".join(wiki_errors))
                    count = mark_ingested(base, selected)
                    data = {"marked_ingested": count, "paths": selected}
                    human = f"已确认整理 {count} 个 Markdown 文件。"
                else:
                    data = {"scanned_at": state["scanned_at"], "pending": pending, "removed": removed}
                    human = f"待整理或已变化：{len(pending)} 个；已删除或移出范围：{len(removed)} 个。\n" + "\n".join(pending + removed)
                emit(args, data, human)
                code = 0
            elif args.command == "validate":
                if args.kind == "wiki":
                    require_v2_project(base)
                    errors = validate_wiki(base, cfg)
                    emit(
                        args,
                        {"valid": not errors, "errors": errors},
                        "检查通过。" if not errors else "检查未通过：\n" + "\n".join(f"- {e}" for e in errors),
                        error=bool(errors),
                    )
                    code = 1 if errors else 0
                else:
                    refuse_unsupported_v2_action(base, f"validate {args.kind}", unit_mode=v2_unit_mode(args))
                    units = resolve_unit_selection(
                        base,
                        cfg,
                        unit_ids=getattr(args, "units", None),
                        changed=bool(getattr(args, "changed", False)),
                        all_units=bool(getattr(args, "all_units", False)),
                    )
                    errors = []
                    for unit in units:
                        errors.extend(
                            validate_unit_report(base, unit) if args.kind == "report" else validate_unit_spec(base, unit)
                        )
                    emit(
                        args,
                        {"valid": not errors, "errors": errors, "units": [unit.id for unit in units]},
                        "检查通过。" if not errors else "检查未通过：\n" + "\n".join(f"- {e}" for e in errors),
                        error=bool(errors),
                    )
                    code = 1 if errors else 0
            elif args.command == "approve":
                refuse_unsupported_v2_action(base, f"approve {args.kind}", unit_mode=v2_unit_mode(args))
                units = resolve_unit_selection(
                    base,
                    cfg,
                    unit_ids=getattr(args, "units", None),
                    changed=bool(getattr(args, "changed", False)),
                    all_units=bool(getattr(args, "all_units", False)),
                )
                approved = []
                stamp = now()
                for unit in units:
                    if args.kind == "report":
                        state = approve_unit_report(base, unit, when=stamp, project_root=root)
                    else:
                        state = approve_unit_spec(base, unit, when=stamp, project_root=root)
                    approved.append({"id": unit.id, "sha256": state[args.kind]["approved_sha256"]})
                assembled = None
                assemble_errors: list[str] = []
                if args.kind == "report":
                    assembled, assemble_errors = assemble_after_report_approvals(base)
                emit(
                    args,
                    {
                        "approved": True,
                        "kind": args.kind,
                        "units": approved,
                        "assembled_report": assembled is not None and not assemble_errors,
                        "assemble_errors": assemble_errors,
                    },
                    f"已批准 {len(approved)} 个单元的 {args.kind}"
                    + ("" if not assemble_errors else "；组装报告失败：" + "；".join(assemble_errors)),
                    error=bool(assemble_errors),
                )
                code = 1 if assemble_errors else 0
            elif args.command == "assemble":
                require_v2_project(base)
                document, errors = assemble_after_report_approvals(base)
                emit(
                    args,
                    {"assembled": not errors, "path": str(base / "reports" / "report.md"), "errors": errors},
                    "已组装 reports/report.md" if not errors else "组装失败：\n" + "\n".join(f"- {e}" for e in errors),
                    error=bool(errors),
                )
                code = 1 if errors else 0
            elif args.command == "slides":
                refuse_unsupported_v2_action(
                    base, f"slides {args.slides_command}", unit_mode=v2_unit_mode(args)
                )
                plan: dict[str, Any] | None = None
                browser_result = None
                output: Path | None = None
                errors: list[str] = []
                selected = resolve_unit_selection(
                    base,
                    cfg,
                    unit_ids=getattr(args, "units", None),
                    changed=bool(getattr(args, "changed", False)),
                    all_units=bool(getattr(args, "all_units", False)),
                )
                selected_ids = [unit.id for unit in selected]
                if args.slides_command == "build":
                    from .assembly import build_units_deck

                    output, errors, plan = build_units_deck(
                        base,
                        cfg,
                        unit_ids=getattr(args, "units", None),
                        changed=bool(getattr(args, "changed", False)),
                        all_units=bool(getattr(args, "all_units", False)),
                        write=True,
                    )
                else:
                    output = base / "slides" / "index.html"
                    from .browser import check_units_on_deck

                    check_result = check_units_on_deck(
                        base, output, selected_ids, browser=bool(args.browser)
                    )
                    errors = list(check_result["errors"])
                    browser_result = check_result.get("browser")
                    plan = {"selected_units": selected_ids, "measured": bool(args.browser)}
                data = {
                    "valid": not errors,
                    "output": str(output) if output else None,
                    "browser": browser_result,
                    "errors": errors,
                    "plan": plan,
                }
                if errors:
                    human = "检查未通过：\n" + "\n".join(f"- {e}" for e in errors)
                else:
                    label = "合并完成" if args.slides_command == "build" else "检查通过"
                    human = f"{label}：{output}"
                emit(args, data, human, error=bool(errors))
                code = 1 if errors else 0
            elif args.command == "units":
                require_v2_project(base)
                data = list_units_status(base, cfg.get("chapters", []))
                human = (
                    f"格式：v2\n单元数：{len(data['units'])}\n"
                    f"缺失产物：{len(data['missing'])}"
                )
                if data["missing"]:
                    human += "\n" + "\n".join(
                        f"- {item['id']} 缺少 {item['artifact']}（{item['path']}）"
                        for item in data["missing"]
                    )
                emit(args, data, human, error=bool(data.get("missing")))
                code = 1 if data.get("missing") else 0
            elif args.command == "migrate":
                if args.rollback:
                    data = rollback_units_migration(base, getattr(args, "stamp", None))
                    emit(args, data, data.get("message", "已回滚"), error=not data.get("rolled_back"))
                    code = 0 if data.get("rolled_back") else 1
                else:
                    if not args.to_units:
                        raise ValueError(
                            "请指定迁移目标或回滚，例如：my-slides migrate --to-units --dry-run"
                            " 或 my-slides migrate --rollback"
                        )
                    if args.dry_run:
                        data = migrate_to_units_preview(base, cfg.get("chapters", []))
                    else:
                        data = migrate_to_units(base, cfg.get("chapters", []))
                    conflicts = data.get("conflicts") or []
                    mapping_gaps = data.get("missing_report_mappings") or []
                    can_migrate = bool(data.get("can_migrate", data.get("migrated")))
                    human = (
                        f"{data.get('message', '迁移完成')}\n"
                        f"预检完成：{'是' if data.get('preview_ok', True) else '否'}\n"
                        f"可迁移/已迁移：{'是' if can_migrate else '否'}\n"
                        f"候选/完成单元：{len(data.get('candidate_units') or data.get('units') or [])}\n"
                        f"冲突：{len(conflicts)}\n"
                        f"警告：{len(data.get('warnings') or [])}\n"
                        f"待确认报告映射：{len(mapping_gaps)}"
                    )
                    if conflicts:
                        human += "\n冲突明细：\n" + "\n".join(f"- {item}" for item in conflicts)
                    if mapping_gaps and not data.get("migrated"):
                        human += "\n映射阻断：\n" + "\n".join(
                            f"- {item['unit_id']}：{item['reason']}" for item in mapping_gaps[:8]
                        )
                    emit(args, data, human, error=bool(data.get("migrated") is False and not args.dry_run and not data.get("preview_ok", True)))
                    if args.dry_run:
                        code = 0 if data.get("preview_ok", True) else 1
                    else:
                        code = 0 if data.get("migrated") else 1
            elif args.command == "doctor":
                required = ["project.yaml", "wiki/README.md", "wiki/index.md", "wiki/log.md", "reports", "specs", "slides"]
                missing = [name for name in required if not (base / name).exists()]
                unit_errors: list[str] = []
                slug_errors = find_slug_collisions([str(item) for item in cfg.get("chapters", [])])
                if format_version == "v2":
                    try:
                        load_units_manifest(base, cfg.get("chapters", []))
                    except UnitsError as exc:
                        unit_errors.append(str(exc))
                        missing.append("units.json（无效）")
                else:
                    missing.append("units.json")
                    unit_errors.append(V1_UNSUPPORTED_MESSAGE)
                renderer = renderer_status()
                browser = browser_status()
                ok = format_version == "v2" and not missing and not unit_errors and not slug_errors
                doctor_data = {
                    "ok": ok,
                    "workspace": str(base),
                    "format_version": format_version,
                    "deprecated": format_version == "v1",
                    "missing": missing,
                    "unit_errors": unit_errors,
                    "slug_errors": slug_errors,
                    "renderer": renderer,
                    "browser": browser,
                }
                if format_version == "v1":
                    doctor_data["deprecation_warning"] = V1_UNSUPPORTED_MESSAGE
                    doctor_human = V1_UNSUPPORTED_MESSAGE
                else:
                    doctor_human = "工作区结构完整。" if ok else "缺少：" + ", ".join(missing + unit_errors + slug_errors)
                emit(args, doctor_data, doctor_human, error=not ok)
                code = 0 if ok else 1
            else:
                # status
                if format_version != "v2":
                    data = {
                        "project": str(root),
                        "format_version": "v1",
                        "deprecated": True,
                        "deprecation_warning": V1_UNSUPPORTED_MESSAGE,
                        "pending_sources": [],
                        "removed_sources": [],
                        "approvals": {},
                        "slides": {"supported": False, "built": False, "current": False},
                    }
                    emit(args, data, V1_UNSUPPORTED_MESSAGE, error=True)
                    code = 1
                else:
                    _, pending, removed = scan_sources(root, base, cfg)
                    unit_status = collect_units_status(
                        base,
                        selected=getattr(args, "units", None),
                        chapters=cfg.get("chapters", []),
                        project_root=root,
                    )
                    approval_status = {
                        "report": {
                            "supported": True,
                            "current": False,
                            "message": "使用 approve report --unit / --changed / --all；状态见 --json 的 units 字段",
                        },
                        "spec": {
                            "supported": True,
                            "current": False,
                            "message": "使用 approve spec --unit / --changed / --all；状态见 --json 的 units 字段",
                        },
                    }
                    slide_status = {
                        "supported": True,
                        "built": (base / "slides" / "index.html").exists(),
                        "current": False,
                        "message": "使用 slides build|check --unit / --changed / --all",
                    }
                    human = (
                        f"项目：{root}\n格式：v2\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
                        f"选定单元：{len(unit_status['selected_units'])}\n"
                        f"受影响：{len(unit_status['affected_units'])}\n"
                        f"可复用：{len(unit_status['reused_units'])}\n"
                        f"阻塞：{len(unit_status['blocked_units'])}\n"
                        "提示：用 --json 查看各单元批准/构建/检查状态"
                    )
                    data = {
                        "project": str(root),
                        "format_version": "v2",
                        "deprecated": False,
                        "pending_sources": pending,
                        "removed_sources": removed,
                        "approvals": approval_status,
                        "slides": slide_status,
                        "selected_units": unit_status["selected_units"],
                        "affected_units": unit_status["affected_units"],
                        "reused_units": unit_status["reused_units"],
                        "blocked_units": unit_status["blocked_units"],
                        "reasons": unit_status["reasons"],
                        "units": unit_status["units"],
                        "dependency_graph": unit_status["dependency_graph"],
                    }
                    emit(args, data, human)
                    code = 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, UnitsError) as exc:
        message = str(exc)
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"错误：{message}", file=sys.stderr)
        code = 2
    except Exception as exc:  # noqa: BLE001 — CLI must never dump a traceback to users
        message = f"未预期错误：{exc}"
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"错误：{message}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
