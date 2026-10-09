"""Initialize a v2 project workspace."""
from __future__ import annotations

import argparse
import re

from ..command_output import emit
from ..project import app_path, now, project_root, read_config, template_chapters, write_config
from ..sources import scan_sources
from ..units import Unit, UnitsError, ensure_v2_directories, load_units_manifest, unit_id_prefix, write_units_manifest
from ..wiki import sync_wiki_index, wiki_instructions


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
    # 已有合法清单时保留单元 ID、数量和顺序；只有缺失或损坏才写入种子单元。
    preserved: list[Unit] | None = None
    if (base / "units.json").is_file():
        try:
            preserved, _manifest_errors = load_units_manifest(base, chapters)
        except UnitsError:
            preserved = None
    if preserved is None:
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
        write_units_manifest(base, unique)
    else:
        unique = preserved
    unit_ids = [unit.id for unit in unique]
    unit_label = (
        f"保留已有 {len(unit_ids)} 个单元"
        if preserved is not None
        else f"{len(unit_ids)} 个种子单元"
    )
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
        f"格式：v2（{unit_label}）\n待整理 Markdown：{len(pending)}"
    )
    emit(args, result, human)
    return 0
