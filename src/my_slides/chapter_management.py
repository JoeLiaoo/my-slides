"""Project-wide operations for the report chapter list (issue #28 phase 4).

A chapter lives in three places: ``project.yaml`` (canonical order), every
``chapter`` field in ``units.json`` (per-unit assignment), and the Wiki
``index.md`` (navigation). The helpers below keep those three in sync while
preserving existing report approvals: chapter renaming only relabels
the chapter string, the unit content and dependency fingerprints stay
identical, so ``refresh_unit_currency`` keeps the approvals current.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .project import read_config, write_config
from .state import refresh_unit_currency, write_unit_state
from .units import (
    Unit,
    UnitsError,
    load_units_manifest,
    unit_paths,
    validate_units,
    write_units_manifest,
)


_CHAPTER_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _config_payload(root: Path, cfg: dict[str, Any]) -> tuple[Path, list[str], list[str], str, str | None, str | None]:
    base = root / "my-slides"
    source_dirs = [str(item) for item in cfg.get("source_dirs") or ["."]]
    chapters = [str(item) for item in cfg.get("chapters") or []]
    brand_color = str(cfg.get("brand_color") or "#A6192E")
    approval_mode = cfg.get("approval_mode")
    reviewer = cfg.get("reviewer")
    cfg_path = base / "project.yaml"
    return cfg_path, source_dirs, chapters, brand_color, approval_mode, reviewer


def _replace_chapter_heading(text: str, old: str, new: str) -> str:
    """Replace ``## <old>`` with ``## <new>`` while preserving surrounding text.

    The Wiki index keeps a comment line below each heading; we leave those
    comments intact so curators do not lose their notes.
    """
    pattern = re.compile(r"^(##\s+)" + re.escape(old) + r"\s*$", re.MULTILINE)
    new_text, count = pattern.subn(lambda _: f"## {new}", text)
    if count == 0:
        # Fallback: tolerate trailing whitespace or full-width punctuation
        # differences by doing a single line rewrite that matches the
        # original line text.
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped == f"## {old}":
                new_text = new_text.replace(raw_line, f"## {new}", 1)
                count += 1
                break
    return new_text, count


def _insert_chapter_heading(text: str, name: str, *, after: str | None = None) -> str:
    """Insert a new ``## <name>`` heading in the configured order.

    Returns the new text; raises UnitsError when no insertion point can be
    determined (this should not happen for normal chapter lists).
    """
    if f"## {name}" in text:
        return text
    headings = [(match.group(0), match.start(), match.group(1)) for match in _CHAPTER_HEADING_RE.finditer(text)]
    insertion_index = len(headings)
    if after is not None:
        for idx, (_line, _start, label) in enumerate(headings):
            if label == after:
                insertion_index = idx + 1
                break
        else:
            raise UnitsError(f"--after 指定章节不存在于 wiki/index.md：{after}")
    block = f"## {name}\n\n<!-- 列出本章相关 wiki 页面及一句话说明。 -->\n"
    if not headings:
        return text.rstrip() + "\n\n" + block
    if insertion_index >= len(headings):
        last_line, last_start, _label = headings[-1]
        head = text[: last_start + len(last_line)]
        tail = text[last_start + len(last_line):]
        return head + "\n\n" + block + tail.lstrip("\n")
    target_line, target_start, _label = headings[insertion_index]
    head = text[: target_start]
    tail = text[target_start:]
    return head + block + tail


def _remove_chapter_heading(text: str, name: str) -> tuple[str, bool]:
    pattern = re.compile(r"^##\s+" + re.escape(name) + r"\s*\n(?:(?!^##\s)[\s\S])*", re.MULTILINE)
    new_text, count = pattern.subn("", text)
    if count:
        return new_text, True
    for raw_line in text.splitlines():
        if raw_line.strip() == f"## {name}":
            start = text.index(raw_line)
            tail = text[start + len(raw_line):]
            next_heading = re.search(r"^##\s+", tail, re.MULTILINE)
            end = start + (next_heading.start() if next_heading else len(tail))
            return text[:start] + text[end:], True
    return text, False


def _reload_chapters(root: Path) -> tuple[Path, list[str], dict[str, Any]]:
    base = root / "my-slides"
    cfg_path = base / "project.yaml"
    cfg = read_config(cfg_path)
    return base, [str(item) for item in cfg.get("chapters", [])], cfg


def _persist_config(root: Path, cfg: dict[str, Any], chapters: list[str]) -> None:
    cfg_path, source_dirs, _old, brand_color, approval_mode, reviewer = _config_payload(root, cfg)
    write_config(
        cfg_path, root, source_dirs, chapters, brand_color,
        approval_mode=approval_mode,
        reviewer=reviewer,
    )


def list_chapters(base: Path, chapters: list[str], units: list[Unit] | None = None) -> dict[str, Any]:
    """Summarize chapters, including the units that live in each one."""
    if units is None:
        # Use chapters=None so orphan chapters do not abort the load; the
        # loader still checks chapter membership but skips the order rule.
        units, _ = load_units_manifest(base, chapters=None)
    by_chapter: dict[str, list[Unit]] = {chapter: [] for chapter in chapters}
    for unit in units:
        by_chapter.setdefault(unit.chapter, []).append(unit)
    rows = []
    for index, chapter in enumerate(chapters):
        occupants = by_chapter.pop(chapter, [])
        rows.append({
            "name": chapter,
            "order": index,
            "unit_count": len(occupants),
            "unit_ids": [unit.id for unit in occupants],
            "wiki_heading": True,  # sync_wiki_index keeps this invariant
        })
    extra = sorted(by_chapter.keys())
    return {
        "chapters": rows,
        "orphan_chapters": extra,  # chapter strings referenced by units but missing from project.yaml
        "count": len(chapters),
    }


def add_chapter(root: Path, name: str, *, after: str | None = None) -> dict[str, Any]:
    """Append or insert a new chapter; refuses duplicates and empty names."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise UnitsError("章节名称不能为空")
    base, chapters, cfg = _reload_chapters(root)
    if cleaned in chapters:
        raise UnitsError(f"章节已存在：{cleaned}")
    if after is not None and after not in chapters:
        raise UnitsError(f"--after 指定章节不存在：{after}")
    index = chapters.index(after) + 1 if after else len(chapters)
    new_chapters = list(chapters)
    new_chapters.insert(index, cleaned)
    wiki_index = base / "wiki" / "index.md"
    if wiki_index.is_file():
        wiki_text = wiki_index.read_text(encoding="utf-8")
        wiki_text = _insert_chapter_heading(wiki_text, cleaned, after=after)
        wiki_index.write_text(wiki_text, encoding="utf-8")
    _persist_config(root, cfg, new_chapters)
    return {
        "added": True,
        "chapter": cleaned,
        "position": index,
        "chapters": new_chapters,
        "wiki_updated": wiki_index.is_file(),
    }


def rename_chapter(root: Path, old: str, new: str) -> dict[str, Any]:
    """Rename a chapter across project.yaml, units.json, and wiki/index.md.

    Approvals stay bound to content hashes and dependency fingerprints, which
    do not change. We rebuild the ``chapter`` field on every affected unit and
    leave the report approval state alone so currency is preserved.
    """
    cleaned_old = (old or "").strip()
    cleaned_new = (new or "").strip()
    if not cleaned_old or not cleaned_new:
        raise UnitsError("章节名称不能为空")
    if cleaned_old == cleaned_new:
        raise UnitsError("新章节名称不能与原名称相同")
    base, chapters, cfg = _reload_chapters(root)
    if cleaned_old not in chapters:
        raise UnitsError(f"章节不存在：{cleaned_old}")
    if cleaned_new in chapters:
        raise UnitsError(f"目标章节已存在：{cleaned_new}")
    units, manifest_errors = load_units_manifest(base, chapters=None)
    if manifest_errors:
        raise UnitsError("；".join(manifest_errors))
    affected = [unit for unit in units if unit.chapter == cleaned_old]
    if any(unit.chapter != cleaned_old for unit in units) is False and not affected:
        # No unit references the old name; still safe to rename headings.
        pass

    # 1. Update units.json: rewrite chapter for every affected unit.
    if affected:
        new_units = [
            Unit(id=unit.id, chapter=cleaned_new if unit.chapter == cleaned_old else unit.chapter,
                 role=unit.role, title=unit.title)
            for unit in units
        ]
        new_chapters = [cleaned_new if chapter == cleaned_old else chapter for chapter in chapters]
        errors = validate_units(new_units, chapters=new_chapters)
        if errors:
            raise UnitsError("重命名会产生无效 units.json：" + "；".join(errors))
        write_units_manifest(base, new_units)
    else:
        new_chapters = [cleaned_new if chapter == cleaned_old else chapter for chapter in chapters]

    # 2. Update project.yaml chapters.
    _persist_config(root, cfg, new_chapters)

    # 3. Update wiki/index.md heading.
    wiki_index = base / "wiki" / "index.md"
    wiki_updated = False
    if wiki_index.is_file():
        wiki_text = wiki_index.read_text(encoding="utf-8")
        renamed, count = _replace_chapter_heading(wiki_text, cleaned_old, cleaned_new)
        if count:
            wiki_index.write_text(renamed, encoding="utf-8")
            wiki_updated = True

    # 4. Refresh every unit's currency so on-disk approval state stays valid.
    refreshed_ids: list[str] = []
    for unit in units:
        refreshed = refresh_unit_currency(base, unit, project_root=root)
        write_unit_state(base, unit.id, refreshed)
        refreshed_ids.append(unit.id)

    return {
        "renamed": True,
        "from": cleaned_old,
        "to": cleaned_new,
        "chapters": new_chapters,
        "affected_units": [unit.id for unit in affected],
        "approvals_preserved": True,
        "reason": (
            "章节重命名只改 chapter 字段，不修改报告内容；"
            "批准绑定的内容哈希与依赖指纹未变，因此批准仍有效；"
            "需要运行 slides build 按新章节同步 Design deck 并重新检查。"
        ),
        "wiki_updated": wiki_updated,
        "refreshed_units": refreshed_ids,
    }


def remove_chapter(root: Path, name: str) -> dict[str, Any]:
    """Refuse when units still reference the chapter; otherwise prune all three stores."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise UnitsError("章节名称不能为空")
    base, chapters, cfg = _reload_chapters(root)
    if cleaned not in chapters:
        raise UnitsError(f"章节不存在：{cleaned}")
    units, manifest_errors = load_units_manifest(base, chapters=None)
    if manifest_errors:
        raise UnitsError("；".join(manifest_errors))
    occupants = [unit for unit in units if unit.chapter == cleaned]
    if occupants:
        raise UnitsError(
            f"章节「{cleaned}」仍有 {len(occupants)} 个小章节："
            + "、".join(unit.id for unit in occupants)
            + "；请先运行 units move 把它们移到其他章节。"
        )
    if chapters == [cleaned]:
        raise UnitsError("项目至少需要保留一个大章节；不能删除唯一章节")
    new_chapters = [chapter for chapter in chapters if chapter != cleaned]
    _persist_config(root, cfg, new_chapters)
    wiki_index = base / "wiki" / "index.md"
    wiki_updated = False
    if wiki_index.is_file():
        wiki_text = wiki_index.read_text(encoding="utf-8")
        pruned, removed = _remove_chapter_heading(wiki_text, cleaned)
        if removed:
            wiki_index.write_text(pruned, encoding="utf-8")
            wiki_updated = True
    return {
        "removed": True,
        "chapter": cleaned,
        "chapters": new_chapters,
        "wiki_updated": wiki_updated,
    }


def move_chapter(root: Path, name: str, *, after: str | None = None, before: str | None = None) -> dict[str, Any]:
    """Reorder chapters in project.yaml and the Wiki index.

    The order in units.json follows project.yaml at validation time, so we
    rewrite both stores together. Report approvals stay bound to
    per-unit content hashes and do not depend on chapter order.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise UnitsError("章节名称不能为空")
    if after is not None and before is not None:
        raise UnitsError("--after 与 --before 只能二选一")
    base, chapters, cfg = _reload_chapters(root)
    if cleaned not in chapters:
        raise UnitsError(f"章节不存在：{cleaned}")
    remaining = [chapter for chapter in chapters if chapter != cleaned]
    if after is not None:
        if after == cleaned:
            raise UnitsError("不能相对自身定位")
        if after not in remaining:
            raise UnitsError(f"--after 指定章节不存在：{after}")
        insert_at = remaining.index(after) + 1
    elif before is not None:
        if before == cleaned:
            raise UnitsError("不能相对自身定位")
        if before not in remaining:
            raise UnitsError(f"--before 指定章节不存在：{before}")
        insert_at = remaining.index(before)
    else:
        insert_at = len(remaining)
    new_chapters = list(remaining)
    new_chapters.insert(insert_at, cleaned)

    # Persist the new order in project.yaml and re-validate units.json. The
    # unit records themselves do not change, but their chapter order must
    # agree with project.yaml.
    units, manifest_errors = load_units_manifest(base, chapters=None)
    if manifest_errors:
        raise UnitsError("；".join(manifest_errors))
    errors = validate_units(units, chapters=new_chapters)
    if errors:
        raise UnitsError("新章节顺序会使 units.json 校验失败：" + "；".join(errors))

    _persist_config(root, cfg, new_chapters)
    write_units_manifest(base, units)

    # Reorder the wiki/index.md headings to match.
    wiki_index = base / "wiki" / "index.md"
    wiki_updated = False
    if wiki_index.is_file():
        wiki_text = wiki_index.read_text(encoding="utf-8")
        new_text = wiki_text
        for heading_name in new_chapters:
            if f"## {heading_name}" not in new_text:
                new_text = _insert_chapter_heading(new_text, heading_name)
        new_text = _reorder_wiki_headings(new_text, new_chapters)
        if new_text != wiki_text:
            wiki_index.write_text(new_text, encoding="utf-8")
            wiki_updated = True

    return {
        "moved": True,
        "chapter": cleaned,
        "position": insert_at,
        "chapters": new_chapters,
        "wiki_updated": wiki_updated,
        "approvals_preserved": True,
    }


def _reorder_wiki_headings(text: str, order: list[str]) -> str:
    """Reorder ``## <chapter>`` blocks in the Wiki index to match ``order``.

    Captures each heading block (heading line + body until the next heading
    of the same level) in the file's current order, then writes them back in
    the requested order. Extra headings such as ``## 补充研究`` are kept at
    the end.
    """
    blocks: list[tuple[str, str, int]] = []
    matches = list(_CHAPTER_HEADING_RE.finditer(text))
    if not matches:
        return text
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        label = match.group(1).strip()
        blocks.append((label, text[start:end], start))
    ordered_labels = [name for name in order if name in {label for label, _, _ in blocks}]
    preserved = [block for block in blocks if block[0] not in ordered_labels]
    label_to_block = {label: body for label, body, _ in blocks}
    rebuilt_blocks: list[str] = []
    for label in ordered_labels:
        rebuilt_blocks.append(label_to_block[label].rstrip("\n") + "\n\n")
    for label, body, _ in preserved:
        rebuilt_blocks.append(body.rstrip("\n") + "\n\n")
    pre = text[: matches[0].start()]
    return pre + "".join(rebuilt_blocks).rstrip("\n") + "\n"
