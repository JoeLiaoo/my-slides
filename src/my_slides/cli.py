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

APP_DIR = "my-slides"
EXCLUDED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__"}
EXCLUDED_FILES = {"agents.md", "claude.md", "gemini.md", "copilot-instructions.md"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slug(value: str) -> str:
    value = re.sub(r"[^\w\u3400-\u9fff.-]+", "-", value.strip().lower(), flags=re.UNICODE)
    return value.strip("-.") or "section"


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
    """Read the small, list-based YAML subset written by this CLI."""
    config: dict[str, Any] = {"source_dirs": ["."], "chapters": []}
    current_list: str | None = None
    if not path.exists():
        return config
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_list:
            config[current_list].append(line[2:].strip().strip('"\''))
            continue
        current_list = None
        match = re.match(r"([\w-]+):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if not value and key in {"source_dirs", "chapters"}:
            config[key] = []
            current_list = key
        elif value:
            config[key] = value.strip('"\'')
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
    base.mkdir(parents=True, exist_ok=True)
    for folder in ("research", "wiki", "reports", "specs", "slides/chapters", ".state"):
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
            readme.write_text(f"# {title}\n\n由当前 agent 按项目 Wiki 和章节配置生成内容。\n", encoding="utf-8")
    write_config(cfg_path, root, source_dirs, chapters, brand_color)
    _, pending, removed = scan_sources(root, base, read_config(cfg_path))
    result = {"project": str(root), "workspace": str(base), "chapters": chapters, "pending_sources": pending, "removed_sources": removed}
    emit(args, result, f"已初始化项目工作区：{base}\n报告章节：{len(chapters)}\n待整理 Markdown：{len(pending)}")
    return 0


def prepare(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    kind = args.kind
    if kind == "spec":
        errors = validate_report(base, cfg)
        if errors:
            raise ValueError("请先完成所有报告章节：" + "；".join(errors))
        if not approval_is_current(base, "report", cfg):
            raise ValueError("请先审阅当前报告并运行 my-slides approve report")
    if kind == "slides":
        errors = validate_spec(base, cfg)
        if errors:
            raise ValueError("请先完成所有 Spec 章节：" + "；".join(errors))
        if not approval_is_current(base, "report", cfg):
            raise ValueError("当前报告版本需要重新审阅，请运行 my-slides approve report")
        if not approval_is_current(base, "spec", cfg):
            raise ValueError("请先审阅当前 Spec 并运行 my-slides approve spec")
    if kind == "report":
        _, pending, removed = scan_sources(root, base, cfg)
        if pending or removed:
            raise ValueError("请先整理有变化或已移除的资料，并运行 my-slides sources mark-ingested")
        wiki_errors = validate_wiki(base, cfg)
        if wiki_errors:
            raise ValueError("请先修复 Wiki 链接：" + "；".join(wiki_errors))
    out_dir = base / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    wiki_snapshot = snapshot_wiki(base, stamp) if kind == "report" else None
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
    elif kind == "report":
        body = f"""# 投资报告撰写任务

{common}

先从 wiki/index.md 按报告章节定位相关页面，阅读后按章节生成完整投资报告。章节与写作要点以项目配置和下方模板为准。资料以普通 Markdown 链接引用 Wiki 或原始资料。不得臆造事实；资料缺口、相互冲突的口径及预测假设请在相关章节说明。

## 输出
在 reports/ 下按章节 slug 创建独立 Markdown 文件，每章以一级标题写明章节名称。保留论证、证据、计算依据和必要限定条件，避免把模板中的每个要点压缩成一句话。

Wiki 索引：wiki/index.md
本次写作依据快照：{wiki_snapshot.relative_to(base).as_posix() if wiki_snapshot else ""}
使用该快照核对撰写依据；报告引用仍链接回对应 Wiki 页面或原始资料。

## 投资报告章节模板
{report_template_text()}
"""
    elif kind == "spec":
        body = f"""# Presentation Spec 生成任务

{common}

只根据已经确认的投资报告生成 Spec。逐章输出到 specs/，每页按以下 Markdown 结构编写，页面 ID 在全项目内唯一：

## Slide 1 — 页面标题
页面 ID：chapter-slug-01
### 目的
### 核心结论
### 展示内容
### 证据与来源
### 限定条件
### 报告段落映射
### 布局意图
### 图标需求
列出 Lucide kebab-case 图标名；不需要时写“无”。

需要定量图表时，在相应页面加入一个或多个 `echarts-spec` JSON 围栏，使用受限图表类型 bar、dot、line、multi-line、scatter、time-scatter、stacked-bar 或 waterfall。示例：

```echarts-spec
{{"type":"bar","title":"收入","categories":["2024","2025"],"values":[10,14],"unit":"亿元","source":"../wiki/财务.md"}}
```

禁止缺失值、臆造数字或混用单位；图表来源应链接报告中引用的同一来源。保留报告论证与信息，不添加新事实。图表仅在数据支持且能改善理解时使用。
"""
    else:
        body = f"""# HTML Slides 生成任务

{common}

只根据已确认的 Presentation Spec，按章节生成 HTML Slides 页面片段，保存为 slides/chapters/章节 slug.html。使用统一 1920×1080、16:9 浅色专业 IC 风格，品牌色 {cfg.get("brand_color", "#A6192E")}。在设计画布尺寸下正文不小于 28px，辅助文字通常不小于 20px。页面包含逐页备注；数据图表使用受限 ECharts 数据标记，图标使用 Lucide 名称标记。使用本机安装的 bluedusk/html-slides skill 生成页面，不引入 CDN 资源。

每个 section class=slide 内必须包含一条 application/json 的 slide-notes 脚本，内容为 JSON 对象。数据图表以 application/json 的 mls-echarts-spec 标记嵌入，图标以 mls-lucide-spec 标记嵌入；CLI 会将它们渲染成内联 SVG。图表只使用 bar、dot、line、multi-line、scatter、time-scatter、stacked-bar、waterfall 类型；所有数值必须明确给出，单位必须一致。图表数据格式为 categories + values，或 categories + series，散点用 points。图标 JSON 至少包含 name 字段，名称使用 Lucide kebab-case。每章 CSS 规则置于 style 元素，并将选择器限制在该章节根节点下。

生成各章后运行 my-slides slides build 合并成可离线打开的 HTML。ECharts/Lucide 本地 SVG 渲染在 Slides 完整实现阶段接入。
"""
    output.write_text(body, encoding="utf-8")
    emit(args, {"task_file": str(output), "kind": kind}, f"已生成交接材料：{output}")
    return 0


def markdown_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    return re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8"))


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
            target = link.split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, flags=re.I) or target.startswith("mailto:"):
                continue
            resolved = (index.parent / target).resolve()
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
            target = link.split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, flags=re.I) or target.startswith("mailto:"):
                continue
            resolved = (page.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{page.relative_to(wiki).as_posix()}：链接目标不存在：{target}")
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
            if not target or target.startswith("#") or re.match(r"^(?:https?|mailto|data):", target, flags=re.I):
                continue
            local = target.split("#", 1)[0].split("?", 1)[0]
            if local and not (path.parent / local).resolve().exists():
                errors.append(f"{path.name}：引用目标不存在：{target}")
    return errors


def validate_spec(base: Path, cfg: dict[str, Any]) -> list[str]:
    folder = base / "specs"
    errors = []
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
            if not re.search(r"页面 ID\s*[：:]\s*\S+", page):
                errors.append(f"{path.name} Slide {slide_number}：缺少页面 ID")
            for heading in required:
                if not re.search(rf"^###\s+{re.escape(heading)}\s*$", page, flags=re.MULTILINE):
                    errors.append(f"{path.name} Slide {slide_number}：缺少 ### {heading}")
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
            if not target or target.startswith("#") or re.match(r"^(?:https?|mailto|data):", target, flags=re.I):
                continue
            local = target.split("#", 1)[0].split("?", 1)[0]
            if local and not (path.parent / local).resolve().exists():
                errors.append(f"{path.name}：来源链接目标不存在：{target}")
    return errors


class SlideFragmentParser(HTMLParser):
    """Collect slide sections from one agent-produced chapter fragment."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

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

    @staticmethod
    def render_tag(tag: str, attrs: list[tuple[str, str | None]], closed: bool = False) -> str:
        rendered = "".join(f' {name}="{html.escape(value or "", quote=True)}"' for name, value in attrs)
        return f"<{tag}{rendered}{' /' if closed else ''}>"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()
        if tag == "script":
            allowed = {"slide-notes", "mls-echarts-spec", "mls-lucide-spec"}
            if attr.get("type") != "application/json" or not (allowed & set(classes)):
                self.errors.append("章节片段包含脚本；只允许 slide-notes、mls-echarts-spec 或 mls-lucide-spec JSON 标记")
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
        if tag in {"iframe", "object", "embed", "base", "link"}:
            self.errors.append(f"章节片段不允许使用 <{tag}>")
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.errors.append(f"章节片段不允许内联事件属性：{name}")
            if name.lower() in {"src", "srcset"} and value and not value.startswith("data:"):
                self.errors.append(f"章节片段包含外部资源：{value}")
            if name.lower() == "href" and value and value.strip().lower().startswith("javascript:"):
                self.errors.append("章节片段不允许 javascript: 链接")
            if name.lower() == "style" and value and re.search(r"url\s*\(|@import", value, flags=re.I):
                self.errors.append("章节片段的 style 属性包含外部导入或 URL")
        if tag == "style":
            self.style = True
        is_slide = "slide" in classes
        if is_slide:
            if self.active:
                self.errors.append("章节片段中不允许嵌套 slide")
            else:
                if tag not in {"section", "div"}:
                    self.errors.append("slide 根元素必须是 <section> 或 <div>")
                slide_id = attr.get("id", "")
                self.active = {"html": [], "notes": [], "assets": [], "has_notes": False, "id": slide_id}
                self.stack = []
        if self.active:
            self.active["html"].append(self.render_tag(tag, attrs))
            if tag not in self.VOID:
                self.stack.append(tag)
        if tag in self.VOID and self.active and is_slide:
            self.errors.append("slide 根元素必须是 section 或 div")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rendered = self.render_tag(tag, attrs, closed=True)
        if self.active:
            self.active["html"].append(rendered)
        elif tag == "style":
            self.errors.append("style 元素不能为空")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self.style = False
        if tag == "script":
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
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
            elif tag in self.stack:
                self.errors.append(f"HTML 标签嵌套顺序错误：</{tag}>")
                self.stack = self.stack[:self.stack.index(tag)]
            if not self.stack:
                slide = self.active
                self.slides.append(slide)
                self.active = None
                self.note_script = False

    def handle_data(self, data: str) -> None:
        if self.style:
            self.css.append(data)
        if self.active:
            self.active["html"].append(data)
            if self.note_script:
                self.active["notes"].append(data)
            if self.asset_script:
                self.asset_data.append(data)

    def handle_entityref(self, name: str) -> None:
        raw = f"&{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_charref(self, name: str) -> None:
        raw = f"&#{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_comment(self, data: str) -> None:
        if self.active:
            self.active["html"].append(f"<!--{data}-->")


def build_slides(base: Path, cfg: dict[str, Any], *, write: bool = True) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    all_slides: list[tuple[str, dict[str, Any]]] = []
    assets_to_render: list[dict[str, Any]] = []
    approved_chart_specs: set[str] = set()
    approved_icons: set[str] = set()
    for chapter in cfg.get("chapters", []):
        spec_path = base / "specs" / f"{slug(chapter)}.md"
        if not spec_path.exists():
            continue
        spec_text = spec_path.read_text(encoding="utf-8")
        for raw_spec in re.findall(r"```echarts-spec\s*\n(.*?)\n```", spec_text, flags=re.DOTALL):
            try:
                chart_spec = json.loads(raw_spec)
                approved_chart_specs.add(json.dumps(chart_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            except json.JSONDecodeError:
                pass
        for icon_section in re.findall(r"^###\s+图标需求\s*$\s*(.*?)(?=^###\s|^##\s|\Z)", spec_text, flags=re.MULTILINE | re.DOTALL):
            if "无" not in icon_section.strip():
                approved_icons.update(re.findall(r"(?<![A-Za-z0-9])([a-z0-9]+(?:-[a-z0-9]+)*)(?![A-Za-z0-9])", icon_section))
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
        marker_pattern = re.compile(
            r'<script\b(?=[^>]*\btype="application/json")(?=[^>]*\bclass="[^\"]*(?:mls-echarts-spec|mls-lucide-spec)[^\"]*")[^>]*>.*?</script>',
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
        source = re.sub(r'\bclass=["\']([^"\']*\bslide\b[^"\']*)["\']',
                        lambda match: f'class="{match.group(1)}" {marker}', source, count=1)
        if number:
            source = re.sub(r'\sactive(?=[\s>])', "", source, count=1)
        elif re.search(r'\bclass=["\'][^"\']*\bactive\b', source) is None:
            source = re.sub(r'\bclass=["\']([^"\']*\bslide\b[^"\']*)["\']',
                            lambda match: f'class="{match.group(1)} active"', source, count=1)
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
            elif (not isinstance(point.get("date"), str) or not isinstance(point.get("y"), (int, float))
                  or isinstance(point.get("y"), bool) or not __import__("math").isfinite(point["y"])):
                raise ValueError("时间散点需要 date 和有限数值 y")
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
    parser.add_argument("--version", action="version", version="my-slides 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="初始化投资项目工作区")
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
    prep = sub.add_parser("prepare", help="生成 agent 阶段交接材料")
    prep.add_argument("kind", choices=("wiki", "report", "spec", "slides"))
    prep.add_argument("--project")
    prep.add_argument("--json", action="store_true")
    prep.add_argument("--question", help="针对项目 Wiki 提出问题；省略时准备资料整理任务")
    validate = sub.add_parser("validate", help="检查 Wiki、报告或 Spec")
    validate.add_argument("kind", choices=("wiki", "report", "spec"))
    validate.add_argument("--project")
    validate.add_argument("--json", action="store_true")
    approve = sub.add_parser("approve", help="记录报告或 Spec 的用户批准版本")
    approve.add_argument("kind", choices=("report", "spec"))
    approve.add_argument("--project")
    approve.add_argument("--json", action="store_true")
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
    for name, help_text in (("build", "合并各章 HTML 片段"), ("check", "检查章节 HTML 和合并文件")):
        command = slides_sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        command.add_argument("--browser", action="store_true", help="用桌面与手机视口运行 Chromium 验证")
    for name, help_text in (("doctor", "检查项目工作区基础结构"), ("status", "查看项目阶段与待整理资料")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
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
            if args.command == "prepare":
                code = prepare(args)
            elif args.command == "sources":
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
                checkers = {
                    "wiki": lambda: validate_wiki(base, cfg),
                    "report": lambda: validate_report(base, cfg),
                    "spec": lambda: validate_spec(base, cfg),
                }
                errors = checkers[args.kind]()
                emit(args, {"valid": not errors, "errors": errors},
                     "检查通过。" if not errors else "检查未通过：\n" + "\n".join(f"- {e}" for e in errors),
                     error=bool(errors))
                code = 1 if errors else 0
            elif args.command == "approve":
                digest, errors = approve_revision(base, cfg, args.kind)
                if errors:
                    emit(args, {"approved": False, "errors": errors},
                         "无法批准：\n" + "\n".join(f"- {e}" for e in errors), error=True)
                    code = 1
                else:
                    emit(args, {"approved": True, "kind": args.kind, "sha256": digest},
                         f"已记录 {args.kind} 批准版本：{digest[:12] if digest else ''}")
                    code = 0
            elif args.command == "slides":
                if not approval_is_current(base, "report", cfg):
                    raise ValueError("当前报告版本需要重新审阅，请运行 my-slides approve report")
                if not approval_is_current(base, "spec", cfg):
                    raise ValueError("当前 Spec 版本需要重新审阅，请运行 my-slides approve spec")
                output, errors = build_slides(base, cfg, write=args.slides_command == "build")
                browser_result = None
                if args.browser and not errors and output and (args.slides_command == "build" or output.exists()):
                    from .browser import check_deck
                    browser_result = check_deck(output)
                    errors.extend(browser_result["errors"])
                if args.slides_command == "check" and not errors:
                    if not output or not output.exists():
                        errors.append("缺少 slides/index.html；请先运行 my-slides slides build")
                    else:
                        generated = output.read_text(encoding="utf-8")
                        if '<meta name="generator" content="my-slides">' not in generated:
                            errors.append("slides/index.html 缺少生成器标记")
                        if generated.count('class="slide ') + generated.count('class="slide"') < len(cfg.get("chapters", [])):
                            errors.append("合并后的演示文稿页面数量异常")
                        state_path = base / ".state" / "slides.json"
                        if not state_path.exists():
                            errors.append("缺少 Slides 构建状态；请重新运行 my-slides slides build")
                        else:
                            state = json.loads(state_path.read_text(encoding="utf-8"))
                            output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
                            if state.get("html_sha256") != output_hash:
                                errors.append("slides/index.html 在构建后已被修改")
                            if state.get("report_sha256") != approval_digest(base, "report", cfg):
                                errors.append("Slides 所依据的报告版本与当前批准版本不一致")
                            if state.get("spec_sha256") != approval_digest(base, "spec", cfg):
                                errors.append("Slides 所依据的 Spec 版本与当前批准版本不一致")
                data = {"valid": not errors, "output": str(output) if output else None, "browser": browser_result, "errors": errors}
                if errors:
                    human = "检查未通过：\n" + "\n".join(f"- {e}" for e in errors)
                else:
                    label = "合并完成" if args.slides_command == "build" else "检查通过"
                    human = f"{label}：{output}"
                emit(args, data, human, error=bool(errors))
                code = 1 if errors else 0
            elif args.command == "doctor":
                required = ["project.yaml", "wiki/README.md", "wiki/index.md", "wiki/log.md", "reports", "specs", "slides"]
                missing = [name for name in required if not (base / name).exists()]
                renderer = renderer_status()
                browser = browser_status()
                emit(args, {"ok": not missing, "workspace": str(base), "missing": missing, "renderer": renderer, "browser": browser},
                     "工作区结构完整。" if not missing else "缺少：" + ", ".join(missing), error=bool(missing))
                code = 1 if missing else 0
            else:
                _, pending, removed = scan_sources(root, base, cfg)
                approvals_path = base / ".state" / "approvals.json"
                approvals = json.loads(approvals_path.read_text(encoding="utf-8")) if approvals_path.exists() else {}
                approval_status = {
                    kind: {"approved": item, "current": approval_is_current(base, kind, cfg)}
                    for kind, item in approvals.items()
                }
                slide_status = {"built": (base / "slides" / "index.html").exists(), "current": slides_is_current(base, cfg)}
                data = {"project": str(root), "pending_sources": pending, "removed_sources": removed, "approvals": approval_status, "slides": slide_status}
                human = (
                    f"项目：{root}\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
                    f"报告已审阅且未变化：{'是' if approval_status.get('report', {}).get('current') else '否'}\n"
                    f"Spec 已审阅且未变化：{'是' if approval_status.get('spec', {}).get('current') else '否'}\n"
                    f"Slides 与当前批准版本一致：{'是' if slide_status['current'] else '否'}"
                )
                emit(args, data, human)
                code = 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
