"""Map report units onto one Design+Slides deck (``my-slides/design/deck``).

Page ids follow the units: a unit's first page is ``<unit-id>`` and further
pages are ``<unit-id>_<suffix>``. Unit ids never contain ``_``, so ownership is
unambiguous. Pages that belong to no unit (for example a hand-made agenda) keep
their place after the page they followed.

Every write goes through :func:`publish_deck_files`: while the Design host is
running it publishes through the host's ``apply`` queue with ``ifMatch``
baselines, so an open editor sees the change and a concurrent hand edit turns
into a reported conflict instead of being overwritten.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .dependencies import fingerprint_file, fingerprint_json
from .design_engine import DEFAULT_BASE_URL, host_reachable, run_agent
from .state import refresh_unit_currency
from .units import Unit, load_units_manifest

DECK_NAME = "deck"
SLIDE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CONTENT_TYPES = {".html": "text/html", ".json": "application/json"}


def projects_root(base: Path) -> Path:
    return base / "design"


def deck_dir(base: Path) -> Path:
    return projects_root(base) / DECK_NAME


def page_unit(page_id: str, unit_ids: set[str]) -> str | None:
    """Return the unit that owns a slide id, or None for free-standing pages."""
    if page_id in unit_ids:
        return page_id
    prefix, sep, _ = page_id.partition("_")
    return prefix if sep and prefix in unit_ids else None


def _page_sort_key(page_id: str) -> tuple[int, str]:
    _, sep, suffix = page_id.partition("_")
    if not sep:
        return (0, "")
    return (int(suffix), "") if suffix.isdigit() else (10**6, suffix)


def disk_pages(deck: Path) -> list[str]:
    folder = deck / "slides"
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.html") if SLIDE_ID_RE.fullmatch(path.stem))


def unit_pages(base: Path, unit_id: str) -> list[str]:
    """Page ids one unit owns, first page first."""
    owned = [page for page in disk_pages(deck_dir(base)) if page_unit(page, {unit_id}) == unit_id]
    return sorted(owned, key=_page_sort_key)


def deck_fingerprint(base: Path) -> str | None:
    """Content fingerprint of deck.json (parsed, so host reformatting is ignored) and every page."""
    deck = deck_dir(base)
    deck_json = deck / "deck.json"
    if not deck_json.is_file():
        return None
    try:
        meta: Any = json.loads(deck_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        meta = deck_json.read_text(encoding="utf-8")
    pages = {page: fingerprint_file(deck / "slides" / f"{page}.html") for page in disk_pages(deck)}
    return fingerprint_json({"deck": meta, "pages": pages})


def plan_order(old_order: list[str], unit_ids: list[str], existing: set[str]) -> list[str]:
    """Order pages by units.json while keeping free-standing pages beside their neighbour."""
    owned = set(unit_ids)
    head: list[str] = []
    groups: dict[str, list[str]] = {unit_id: [] for unit_id in unit_ids}
    current: str | None = None
    for page in dict.fromkeys(old_order):
        if page not in existing:
            continue
        owner = page_unit(page, owned)
        if owner:
            current = owner
        (groups[current] if current else head).append(page)
    placed = set(head).union(*groups.values())
    for page in sorted(existing - placed, key=_page_sort_key):
        owner = page_unit(page, owned)
        if owner:
            groups[owner].append(page)
    return head + [page for unit_id in unit_ids for page in groups[unit_id]]


def _placeholder(unit: Unit, project_title: str) -> str:
    title = html.escape(unit.title or unit.id)
    if unit.role == "cover":
        return (
            f'<section id="{unit.id}" data-transition="fade" style="background:#12141a;color:#f4f6fb;'
            "font-family:Arial, Helvetica, sans-serif;padding:160px;display:flex;flex-direction:column;"
            'gap:28px;justify-content:center">\n'
            f'<h1 style="font-size:96px;font-weight:700;line-height:1.1">{html.escape(project_title)}</h1>\n'
            '<p style="font-size:36px;color:#a8b0c2">[待写：封面副标题]</p>\n</section>\n'
        )
    return (
        f'<section id="{unit.id}" data-transition="fade" style="background:#f7f5f0;color:#22252b;'
        "font-family:Arial, Helvetica, sans-serif;padding:128px;display:flex;flex-direction:column;"
        'gap:40px;justify-content:center">\n'
        f'<p style="font-size:28px;color:#6b6f76">{html.escape(unit.chapter)}</p>\n'
        f'<h2 style="font-size:72px;font-weight:700;line-height:1.1">{title}</h2>\n'
        f'<p style="font-size:32px;color:#6b6f76">[待写：依据 reports/units/{unit.id}.md 撰写本页]</p>\n'
        "</section>\n"
    )


def _read_deck(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file():
        return {"v": 4, "lists": "css", "title": title, "order": [], "cover": "",
                "sections": {}, "faces": {}, "designSystems": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"deck.json 不是 JSON 对象：{path}")
    return data


def _dump_deck(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def publish_deck_files(base: Path, files: dict[str, str | None]) -> str:
    """Write (text) or delete (None) files given relative to the deck directory.

    Returns ``"host"`` when published through the running Design host,
    ``"disk"`` when written directly, or ``"none"`` when nothing changed.
    """
    deck = deck_dir(base)
    current = {rel: (deck / rel).read_bytes() if (deck / rel).is_file() else None for rel in files}
    changes = {
        rel: content for rel, content in files.items()
        if not (content is None and current[rel] is None)
        and not (content is not None and current[rel] == content.encode("utf-8"))
    }
    if not changes:
        return "none"
    # 宿主只认识已有 deck.json 的项目；第一次创建时还没有编辑器能打开它，直接写盘。
    if (deck / "deck.json").is_file() and host_reachable():
        batch: dict[str, dict[str, Any]] = {}
        for rel, content in changes.items():
            baseline = hashlib.sha256(current[rel]).hexdigest() if current[rel] is not None else None
            if content is None:
                batch[f"project/{rel}"] = {"delete": True, "ifMatch": baseline}
            else:
                batch[f"project/{rel}"] = {
                    "base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                    "contentType": CONTENT_TYPES.get(Path(rel).suffix, "application/octet-stream"),
                    "ifMatch": baseline,
                }
        with tempfile.TemporaryDirectory() as folder:
            batch_path = Path(folder) / "batch.json"
            batch_path.write_text(json.dumps({"files": batch}), encoding="utf-8")
            _, result = run_agent(["apply", DECK_NAME, "--batch", str(batch_path)], projects_root(base),
                                  base_url=DEFAULT_BASE_URL)
        if result.get("ok"):
            return "host"
        if result.get("code") == "conflict":
            paths = [str(item.get("path", "")).removeprefix("project/") for item in result.get("paths") or []]
            raise ValueError("Design 编辑器里这些文件已被改动，未写入任何文件：" + ("、".join(paths) or "未知")
                             + "。请在 5173 上保存或放弃改动后重跑。")
        # host_unavailable 也包括宿主在服务别的 --projects 目录：那时本项目没有打开的编辑器，可以直接写盘。
        if result.get("code") != "host_unavailable":
            raise ValueError(f"Design 发布失败：{result.get('code')} {result.get('message', '')}".strip())
    for rel, content in changes.items():
        path = deck / rel
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return "disk"


PLACEHOLDER_MARK = "[待写："


def placeholder_pages(base: Path, unit_id: str) -> list[str]:
    """Pages of a unit that still carry the placeholder text written by ``sync_deck``."""
    slides = deck_dir(base) / "slides"
    return [page for page in unit_pages(base, unit_id)
            if PLACEHOLDER_MARK in (slides / f"{page}.html").read_text(encoding="utf-8")]


def unapproved_reports(base: Path, units: list[Unit]) -> list[str]:
    return [
        unit.id for unit in units
        if not refresh_unit_currency(base, unit, project_root=base.parent)["report"]["current"]
    ]


def unit_needs_pages(base: Path, unit_id: str) -> bool:
    """True while a unit has no page or still shows a ``[待写：…]`` placeholder."""
    pages = unit_pages(base, unit_id)
    return not pages or any(
        PLACEHOLDER_MARK in (deck_dir(base) / "slides" / f"{page}.html").read_text(encoding="utf-8")
        for page in pages
    )


def sync_deck(base: Path, cfg: dict[str, Any], selected: list[Unit], *, write: bool = True) -> dict[str, Any]:
    """Create or update deck.json from units.json; add placeholders for selected units.

    Existing slide files are never rewritten: humans may have edited them on 5173.
    ``write=False`` only reports what would change.
    """
    units, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        raise ValueError("；".join(errors))
    blocked = unapproved_reports(base, selected)
    if blocked:
        raise ValueError("以下单元的报告尚未获得当前有效批准，不能开始写页：" + "、".join(blocked))
    deck = deck_dir(base)
    title = str(cfg.get("project") or base.parent.name)
    deck_path = deck / "deck.json"
    data = _read_deck(deck_path, title)
    original = json.loads(json.dumps(data)) if deck_path.is_file() else None
    existing = set(disk_pages(deck))
    unit_ids = {unit.id for unit in units}
    writes: dict[str, str | None] = {}
    created: list[str] = []
    for unit in selected:
        if not any(page_unit(page, unit_ids) == unit.id for page in existing):
            writes[f"slides/{unit.id}.html"] = _placeholder(unit, title)
            existing.add(unit.id)
            created.append(unit.id)
    order = plan_order(list(data.get("order") or []), [unit.id for unit in units], existing)
    sections = {name: value for name, value in dict(data.get("sections") or {}).items()
                if isinstance(value, dict) and value.get("start") in order}
    chapter_of = {unit.id: unit.chapter for unit in units}
    for chapter in dict.fromkeys(unit.chapter for unit in units):
        pages = [page for page in order if chapter_of.get(page_unit(page, unit_ids) or "") == chapter]
        if pages:
            previous = sections.get(chapter) or {}
            sections[chapter] = {"description": previous.get("description") or chapter, "start": pages[0]}
        else:
            sections.pop(chapter, None)
    cover_unit = next((unit.id for unit in units if unit.role == "cover" and unit.id in order), None)
    data.update({"order": order, "sections": sections, "cover": cover_unit or (order[0] if order else "")})
    data.setdefault("title", title)
    # 内容相同就不写，避免打断 5173 上正在编辑的窗口。
    changed = data != original
    if changed:
        writes["deck.json"] = _dump_deck(data)
    via = publish_deck_files(base, writes) if writes and write else "none"
    return {
        "deck_dir": str(deck),
        "projects_root": str(projects_root(base)),
        "deck_changed": changed,
        "written_via": via,
        "created_pages": created,
        "order": order,
        "unmapped_pages": [page for page in order if not page_unit(page, unit_ids)],
        "units_without_pages": [unit.id for unit in units
                                if not any(page_unit(page, unit_ids) == unit.id for page in order)],
    }


def _retarget_section_id(text: str, old: str, new: str) -> str:
    pattern = r'(<section\b[^>]*?\bid=)(["\'])' + re.escape(old) + r"\2"
    return re.sub(pattern, lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(2)}", text, count=1)


def remap_unit_pages(base: Path, old_id: str, new_id: str | None) -> dict[str, str | None]:
    """Batch that renames a unit's pages to ``new_id`` (or drops them for None).

    deck.json order, cover, and section starts follow the change; the next
    ``slides build`` recomputes the rest from units.json.
    """
    deck = deck_dir(base)
    deck_path = deck / "deck.json"
    pages = unit_pages(base, old_id)
    if not pages or not deck_path.is_file():
        return {}
    mapping = {page: (new_id + page[len(old_id):] if new_id else None) for page in pages}
    writes: dict[str, str | None] = {}
    for old_page, new_page in mapping.items():
        writes[f"slides/{old_page}.html"] = None
        if new_page:
            text = (deck / "slides" / f"{old_page}.html").read_text(encoding="utf-8")
            writes[f"slides/{new_page}.html"] = _retarget_section_id(text, old_page, new_page)
    data = _read_deck(deck_path, "")
    old_order = list(data.get("order") or [])
    order = [mapping.get(page, page) for page in old_order]
    order = [page for page in order if page]

    def survivor(page: str) -> str | None:
        if page not in mapping:
            return page
        if mapping[page]:
            return mapping[page]
        later = old_order[old_order.index(page) + 1:] if page in old_order else []
        return next((item for item in later if item not in mapping), None)

    sections = {}
    for name, value in dict(data.get("sections") or {}).items():
        start = survivor(value.get("start")) if isinstance(value, dict) else None
        if start:
            sections[name] = {**value, "start": start}
    cover = survivor(str(data.get("cover") or "")) if data.get("cover") else ""
    data.update({"order": order, "sections": sections, "cover": cover or (order[0] if order else "")})
    writes["deck.json"] = _dump_deck(data)
    return writes
