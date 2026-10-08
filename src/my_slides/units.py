"""Unit-format schema, path helpers, validation, and read-only migration preview.

Step 1 of the Report → Spec → HTML unit model (#1): v1 chapter projects stay on
the existing layout; v2 projects are identified by my-slides/units.json.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

SCHEMA_VERSION = 2
UNIT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UNIT_ROLES = frozenset({"cover", "content"})
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Reference definitions: [label]: path, [label]: <path>, optional title suffix.
# Footnote definitions ([^1]: …) are excluded via a negative lookahead on ^.
MARKDOWN_REF_DEF_RE = re.compile(
    r"^(\[[^\]\^\n][^\]\n]*\]:\s*)(?:<([^>\n]+)>|(\S+))(.*)$",
    flags=re.MULTILINE,
)
MARKDOWN_FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]:", flags=re.MULTILINE)
SPEC_PAGE_RE = re.compile(r"^##\s+Slide\s+(\d+)\s+[—-].*$", flags=re.MULTILINE)
SPEC_PAGE_ID_RE = re.compile(r"^页面 ID\s*[：:]\s*(\S+)\s*$", flags=re.MULTILINE)
SPEC_ROLE_RE = re.compile(r"^页面角色\s*[：:]\s*(cover|content)\s*$", flags=re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class Unit:
    id: str
    chapter: str
    role: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class UnitPaths:
    """Resolved paths for one unit inside a my-slides workspace."""

    report: Path
    spec: Path
    page: Path
    preview: Path
    state: Path


class UnitsError(ValueError):
    """Raised when units.json or derived unit structure is invalid."""


def slug(value: str) -> str:
    value = re.sub(r"[^\w\u3400-\u9fff.-]+", "-", value.strip().lower(), flags=re.UNICODE)
    return value.strip("-.") or "section"


def unit_id_prefix(value: str, *, fallback: str) -> str:
    """Build a UNIT_ID_RE-safe prefix; Chinese chapter titles fall back to an ASCII token."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned if UNIT_ID_RE.fullmatch(cleaned) else fallback


def encode_link_path(relative: Path) -> str:
    """Percent-encode each path segment so # and spaces stay in the path, not the fragment."""
    parts: list[str] = []
    for segment in relative.as_posix().split("/"):
        if segment in {"", ".", ".."}:
            parts.append(segment)
        else:
            parts.append(quote(segment, safe=""))
    return "/".join(parts)


def strip_markdown_link_target(raw: str) -> str:
    """Drop optional Markdown link title and angle brackets from a destination."""
    target = (raw or "").strip()
    if target.startswith("<") and ">" in target:
        return target[1:].partition(">")[0].strip()
    match = re.match(
        r'^(.*?)(?:\s+(?:"(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\'|\((?:\\.|[^)])*\)))\s*$',
        target,
    )
    if match and match.group(1).strip():
        return match.group(1).strip()
    return target


def strip_markdown_code_regions(text: str) -> str:
    """Blank out fenced/inline code so link scanners ignore examples inside code."""
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", " ", text)


def resolve_local_markdown_path(target: str, base_file: Path) -> Path | None:
    """Resolve one local Markdown link from base_file; None means external/skip.

    Shared by v1 validators and v2 assemble so `%20` / percent-encoding behave the same.
    """
    target = strip_markdown_link_target(target or "")
    if _is_external_link(target):
        return None
    raw_path, _, _ = target.partition("#")
    decoded = unquote(raw_path.split("?", 1)[0])
    if not decoded:
        return None
    return (base_file.parent / decoded).resolve()


def units_manifest_path(base: Path) -> Path:
    return base / "units.json"


def detect_format_version(base: Path) -> str:
    """Return 'v2' when units.json exists; otherwise 'v1' chapter layout."""
    return "v2" if units_manifest_path(base).is_file() else "v1"


def unit_paths(base: Path, unit_id: str) -> UnitPaths:
    if not UNIT_ID_RE.fullmatch(unit_id):
        raise UnitsError(f"非法单元 ID：{unit_id}")
    return UnitPaths(
        report=base / "reports" / "units" / f"{unit_id}.md",
        spec=base / "specs" / "units" / f"{unit_id}.md",
        page=base / "slides" / "pages" / f"{unit_id}.html",
        preview=base / "slides" / "previews" / f"{unit_id}.html",
        state=base / ".state" / "units" / f"{unit_id}.json",
    )


def assembled_report_path(base: Path) -> Path:
    return base / "reports" / "report.md"


def ensure_v2_directories(base: Path) -> None:
    for relative in (
        "reports/units",
        "specs/units",
        "slides/pages",
        "slides/previews",
        ".state/units",
        ".state/cache",
        ".state/revisions",
        ".state/deliveries",
    ):
        (base / relative).mkdir(parents=True, exist_ok=True)


def _normalize_unit_entry(raw: Any, index: int) -> Unit:
    if not isinstance(raw, dict):
        raise UnitsError(f"units[{index}] 必须是对象")
    unit_id = raw.get("id")
    chapter = raw.get("chapter")
    role = raw.get("role")
    if not isinstance(unit_id, str) or not UNIT_ID_RE.fullmatch(unit_id):
        raise UnitsError(f"units[{index}].id 非法：{unit_id!r}（仅允许小写字母、数字与连字符）")
    if not isinstance(chapter, str) or not chapter.strip():
        raise UnitsError(f"units[{index}].chapter 不能为空")
    if not isinstance(role, str) or role not in UNIT_ROLES:
        raise UnitsError(f"units[{index}].role 必须是 cover 或 content")
    unknown = sorted(set(raw) - {"id", "chapter", "role"})
    if unknown:
        raise UnitsError(f"units[{index}] 含未知字段：{', '.join(unknown)}")
    return Unit(id=unit_id, chapter=chapter.strip(), role=role)


def validate_units(units: list[Unit], chapters: list[str] | None = None) -> list[str]:
    """Validate unit identity rules. When chapters is None, skip chapter membership/order checks."""
    errors: list[str] = []
    if not units:
        errors.append("units.json 至少需要一个单元")
        return errors
    seen: set[str] = set()
    for unit in units:
        if unit.id in seen:
            errors.append(f"单元 ID 重复：{unit.id}")
        seen.add(unit.id)
        if not UNIT_ID_RE.fullmatch(unit.id):
            errors.append(f"单元 ID 非法：{unit.id}")
        if unit.role not in UNIT_ROLES:
            errors.append(f"单元 {unit.id} 的角色非法：{unit.role!r}")
        if chapters is not None and unit.chapter not in chapters:
            errors.append(f"单元 {unit.id} 的章节不存在于 project.yaml：{unit.chapter}")
    covers = [unit for unit in units if unit.role == "cover"]
    if len(covers) != 1:
        errors.append("全套必须且只能包含一个 cover 单元")
    elif units[0].role != "cover":
        errors.append("cover 单元必须位于 units 数组首位")
    if chapters is not None:
        chapter_order = [chapter for chapter in chapters if any(unit.chapter == chapter for unit in units)]
        last_index = -1
        for unit in units:
            try:
                index = chapter_order.index(unit.chapter)
            except ValueError:
                continue
            if index < last_index:
                errors.append(f"单元顺序与 project.yaml 章节顺序冲突：{unit.id}（章节 {unit.chapter}）")
                break
            last_index = index
    return errors


def load_units_manifest(base: Path, chapters: list[str] | None = None) -> tuple[list[Unit], list[str]]:
    path = units_manifest_path(base)
    if not path.is_file():
        raise UnitsError("缺少 units.json；当前项目仍是 v1 章节格式")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnitsError(f"units.json 不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise UnitsError("units.json 根节点必须是对象")
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise UnitsError(f"units.json schema_version 必须为 {SCHEMA_VERSION}，实际为 {schema_version!r}")
    raw_units = payload.get("units")
    if not isinstance(raw_units, list):
        raise UnitsError("units.json 的 units 必须是数组")
    units = [_normalize_unit_entry(item, index) for index, item in enumerate(raw_units)]
    errors = validate_units(units, chapters)
    if errors:
        raise UnitsError("；".join(errors))
    return units, errors


def dump_units_manifest(units: list[Unit]) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "units": [unit.to_dict() for unit in units],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_units_manifest(base: Path, units: list[Unit]) -> Path:
    path = units_manifest_path(base)
    path.write_text(dump_units_manifest(units), encoding="utf-8")
    return path


def list_units_status(base: Path, chapters: list[str]) -> dict[str, Any]:
    """Describe the unit inventory for CLI `units list`."""
    version = detect_format_version(base)
    if version == "v1":
        return {
            "format_version": "v1",
            "schema_version": None,
            "units": [],
            "missing": [],
            "message": "当前为 v1 章节格式；运行 my-slides migrate --to-units --dry-run 查看迁移预检",
        }
    units, _ = load_units_manifest(base, chapters)
    missing: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    for unit in units:
        paths = unit_paths(base, unit.id)
        presence = {
            "report": paths.report.is_file(),
            "spec": paths.spec.is_file(),
            "page": paths.page.is_file(),
        }
        path_map = {"report": paths.report, "spec": paths.spec, "page": paths.page}
        for kind, present in presence.items():
            if not present:
                missing.append({
                    "id": unit.id,
                    "artifact": kind,
                    "path": path_map[kind].relative_to(base).as_posix(),
                })
        rows.append({
            "id": unit.id,
            "chapter": unit.chapter,
            "role": unit.role,
            "artifacts": presence,
        })
    return {
        "format_version": "v2",
        "schema_version": SCHEMA_VERSION,
        "units": rows,
        "missing": missing,
        "selected_units": [unit.id for unit in units],
        "affected_units": [],
        "reused_units": [],
        "blocked_units": [item["id"] for item in missing],
        "reasons": {
            item["id"]: f"缺少 {item['artifact']}：{item['path']}"
            for item in missing
        },
    }


def _is_external_link(target: str) -> bool:
    if not target or target.startswith("#") or target.startswith("mailto:"):
        return True
    parsed = urlparse(target)
    return bool(parsed.scheme)


def rewrite_link_target(target: str, *, source_file: Path, destination_file: Path) -> str | None:
    """Rewrite one local link target; return None when the target should be left unchanged."""
    cleaned = strip_markdown_link_target(target.strip())
    if _is_external_link(cleaned):
        return None
    # Split on an unencoded fragment marker before decoding path escapes like %23.
    raw_path, separator, anchor = cleaned.partition("#")
    decoded_path = unquote(raw_path)
    if not decoded_path:
        return None
    resolved = (source_file.parent / decoded_path).resolve()
    try:
        relative = Path(os_path_relative_to(resolved, destination_file.parent.resolve()))
    except ValueError:
        return None
    rewritten = encode_link_path(relative)
    if separator:
        rewritten = f"{rewritten}#{anchor}"
    return rewritten


def rewrite_relative_links(text: str, *, source_file: Path, destination_file: Path) -> str:
    """Rewrite inline and reference-definition Markdown links for assembly into report.md."""

    def replace_inline(match: re.Match[str]) -> str:
        raw_target = match.group(1)
        path_only = strip_markdown_link_target(raw_target)
        rewritten = rewrite_link_target(path_only, source_file=source_file, destination_file=destination_file)
        if rewritten is None:
            return match.group(0)
        # Preserve an optional title suffix after the destination path.
        suffix = raw_target[len(path_only):] if raw_target.startswith(path_only) else ""
        if not suffix and raw_target != path_only:
            # Title form: path + whitespace + quoted title
            stripped = raw_target.strip()
            if stripped.startswith(path_only):
                suffix = stripped[len(path_only):]
            else:
                suffix = ""
        return match.group(0).replace(raw_target, f"{rewritten}{suffix}" if suffix else rewritten)

    def replace_ref_def(match: re.Match[str]) -> str:
        prefix, angled, bare, suffix = match.group(1), match.group(2), match.group(3), match.group(4)
        target = angled if angled is not None else bare
        rewritten = rewrite_link_target(target, source_file=source_file, destination_file=destination_file)
        if rewritten is None:
            return match.group(0)
        if angled is not None:
            return f"{prefix}<{rewritten}>{suffix}"
        return f"{prefix}{rewritten}{suffix}"

    text = MARKDOWN_LINK_RE.sub(replace_inline, text)
    return MARKDOWN_REF_DEF_RE.sub(replace_ref_def, text)


def iter_local_markdown_targets(text: str) -> list[str]:
    text = strip_markdown_code_regions(text)
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        if re.match(r"^\[\^[^\]]+\]", match.group(0)):
            continue
        targets.append(strip_markdown_link_target(match.group(1)))
    for match in MARKDOWN_REF_DEF_RE.finditer(text):
        angled, bare = match.group(2), match.group(3)
        targets.append(strip_markdown_link_target((angled if angled is not None else bare) or ""))
    return targets


def validate_local_markdown_links(text: str, base_file: Path) -> list[str]:
    """Ensure rewritten local Markdown targets resolve from base_file's directory."""
    errors: list[str] = []
    for target in iter_local_markdown_targets(text):
        resolved = resolve_local_markdown_path(target, base_file)
        if resolved is not None and not resolved.exists():
            errors.append(f"组装后本地链接失效：{target}")
    return errors


def os_path_relative_to(path: Path, start: Path) -> Path:
    """Cross-drive-safe relative path (P3-13); prefers os.path.relpath."""
    import os

    try:
        return Path(os.path.relpath(str(path.resolve()), start=str(start.resolve())))
    except ValueError as exc:
        raise ValueError(f"{path} is not relative to {start}") from exc


def assemble_report(base: Path, units: list[Unit] | None = None, *, write: bool = True) -> tuple[str, list[str]]:
    """Concatenate report units into reports/report.md with rewritten local links.

    On validation or link failure the existing report.md is left untouched.
    """
    destination = assembled_report_path(base)
    if units is None:
        try:
            units, _ = load_units_manifest(base, chapters=None)
        except UnitsError as exc:
            return "", [str(exc)]
    else:
        structure_errors = validate_units(units, chapters=None)
        if structure_errors:
            return "", structure_errors
    errors: list[str] = []
    parts: list[str] = []
    for unit in units:
        path = unit_paths(base, unit.id).report
        if not path.is_file():
            errors.append(f"缺少报告单元：reports/units/{unit.id}.md")
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            errors.append(f"报告单元为空：{unit.id}")
            continue
        rewritten = rewrite_relative_links(text, source_file=path, destination_file=destination)
        parts.append(rewritten.rstrip() + "\n")
    if errors:
        return "", errors
    document = "\n".join(parts).rstrip() + "\n"
    link_errors = validate_local_markdown_links(document, destination)
    if link_errors:
        return "", link_errors
    if write:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding="utf-8")
    return document, []


def _parse_chapter_html_boundaries(html_text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Reuse the merge-time SlideFragmentParser so unclosed tags behave identically."""
    # Lazy import: cli imports units at module load; avoid a circular import at import time.
    from .cli import SlideFragmentParser

    parser = SlideFragmentParser()
    parser.feed(html_text)
    parser.close()
    slides = [
        {
            "id": slide.get("id", "") or "",
            "role": slide.get("role", "") or "",
            "tag": "section",
        }
        for slide in parser.slides
    ]
    return slides, list(parser.errors)


def _extract_spec_pages(text: str) -> list[dict[str, str]]:
    matches = list(SPEC_PAGE_RE.finditer(text))
    pages: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page = text[match.start():end]
        page_id_match = SPEC_PAGE_ID_RE.search(page)
        role_match = SPEC_ROLE_RE.search(page)
        pages.append({
            "slide_number": match.group(1),
            "id": page_id_match.group(1) if page_id_match else "",
            "role": role_match.group(1).lower() if role_match else "",
            "title": match.group(0),
        })
    return pages


def migrate_to_units_preview(base: Path, chapters: list[str]) -> dict[str, Any]:
    """Read-only scan of a v1 chapter project; never writes."""
    if detect_format_version(base) == "v2":
        return {
            "dry_run": True,
            "preview_ok": True,
            "format_version": "v2",
            "can_migrate": False,
            "candidate_units": [],
            # Not a conflict — the project is already on the target format.
            "conflicts": [],
            "warnings": ["项目已是 v2 单元格式，无需迁移"],
            "missing_report_mappings": [],
            "html_boundaries": [],
            "blocked_units": [],
            "message": "项目已是 v2 单元格式；预检完成，但无需迁移。",
        }

    candidate_units: list[dict[str, Any]] = []
    conflicts: list[str] = []
    warnings: list[str] = []
    missing_report_mappings: list[dict[str, str]] = []
    html_boundaries: list[dict[str, Any]] = []
    seen_ids: dict[str, str] = {}
    global_order = 0

    def register_candidate(unit: dict[str, Any]) -> None:
        nonlocal global_order
        unit_id = unit["id"]
        chapter = unit["chapter"]
        if unit_id in seen_ids:
            conflicts.append(f"跨章重复页面 ID：{unit_id}（{seen_ids[unit_id]} 与 {chapter}）")
        else:
            seen_ids[unit_id] = chapter
        if not UNIT_ID_RE.fullmatch(unit_id):
            conflicts.append(f"候选单元 ID 非法：{unit_id}（章节 {chapter}）")
        if unit.get("role") not in UNIT_ROLES:
            conflicts.append(f"候选单元角色非法：{unit.get('role')!r}（{unit_id}）")
        candidate_units.append(unit)
        global_order += 1

    for chapter_index, chapter in enumerate(chapters, start=1):
        chapter_slug = slug(chapter)
        id_prefix = unit_id_prefix(chapter, fallback=f"chapter-{chapter_index:02d}")
        report_path = base / "reports" / f"{chapter_slug}.md"
        spec_path = base / "specs" / f"{chapter_slug}.md"
        html_path = base / "slides" / "chapters" / f"{chapter_slug}.html"

        report_exists = report_path.is_file()
        spec_pages: list[dict[str, str]] = []
        if spec_path.is_file():
            spec_pages = _extract_spec_pages(spec_path.read_text(encoding="utf-8"))
        else:
            warnings.append(f"缺少 Spec 章节：specs/{chapter_slug}.md")

        html_slides: list[dict[str, str]] = []
        if html_path.is_file():
            try:
                html_slides, parse_errors = _parse_chapter_html_boundaries(
                    html_path.read_text(encoding="utf-8")
                )
                for issue in parse_errors:
                    warnings.append(f"slides/chapters/{chapter_slug}.html：{issue}")
            except Exception as exc:  # noqa: BLE001 - preview must stay read-only and resilient
                conflicts.append(f"HTML 解析失败：slides/chapters/{chapter_slug}.html（{exc}）")
            html_boundaries.append({
                "chapter": chapter,
                "path": f"slides/chapters/{chapter_slug}.html",
                "slide_count": len(html_slides),
                "slides": html_slides,
            })
        else:
            warnings.append(f"缺少 Slides 章节：slides/chapters/{chapter_slug}.html")

        if not spec_pages and not html_slides:
            # Fall back to one content candidate per chapter so dry-run still surfaces work.
            if report_exists or chapter == chapters[0]:
                fallback_id = "cover" if not candidate_units else f"{id_prefix}-01"
                role = "cover" if not candidate_units else "content"
                register_candidate({
                    "id": fallback_id,
                    "chapter": chapter,
                    "role": role,
                    "source": "chapter-fallback",
                    "report_path": f"reports/{chapter_slug}.md" if report_exists else None,
                    "spec_path": None,
                    "html_path": None,
                })
                if not report_exists:
                    missing_report_mappings.append({
                        "unit_id": fallback_id,
                        "chapter": chapter,
                        "reason": "缺少对应报告章节文件，无法在不猜测的情况下建立报告映射",
                    })
            continue

        page_count = max(len(spec_pages), len(html_slides), 1)
        for index in range(page_count):
            spec_page = spec_pages[index] if index < len(spec_pages) else None
            html_slide = html_slides[index] if index < len(html_slides) else None
            unit_id = ""
            role = "content"
            source = "inferred"
            if spec_page and spec_page["id"]:
                unit_id = spec_page["id"]
                role = spec_page["role"] or role
                source = "spec-page-id"
            elif html_slide and html_slide["id"]:
                unit_id = html_slide["id"]
                role = html_slide["role"] or role
                source = "html-slide-id"
            else:
                unit_id = "cover" if global_order == 0 else f"{id_prefix}-{index + 1:02d}"
                role = "cover" if global_order == 0 else "content"
                source = "generated-fallback"
                warnings.append(
                    f"章节 {chapter} 第 {index + 1} 页缺少稳定页面 ID，预检仅给出候选 {unit_id}，正式迁移前需人工确认"
                )

            if spec_page and html_slide:
                if spec_page["id"] and html_slide["id"] and spec_page["id"] != html_slide["id"]:
                    conflicts.append(
                        f"章节 {chapter} 第 {index + 1} 页 Spec ID（{spec_page['id']}）与 HTML id（{html_slide['id']}）不一致"
                    )
                if spec_page["role"] and html_slide["role"] and spec_page["role"] != html_slide["role"]:
                    conflicts.append(
                        f"章节 {chapter} 第 {index + 1} 页 Spec 角色（{spec_page['role']}）与 HTML data-page-role（{html_slide['role']}）不一致"
                    )

            if index >= len(spec_pages) and html_slide:
                missing_report_mappings.append({
                    "unit_id": unit_id,
                    "chapter": chapter,
                    "reason": "HTML 有额外页面，但 Spec 未提供对应分页，无法确定报告映射",
                })
            if index >= len(html_slides) and spec_page:
                warnings.append(f"章节 {chapter} Spec 第 {index + 1} 页在 HTML 中缺少对应 slide 边界")

            if not report_exists:
                missing_report_mappings.append({
                    "unit_id": unit_id,
                    "chapter": chapter,
                    "reason": "缺少报告章节文件；报告语义拆分需 Agent/用户审阅，不能按页码猜测",
                })
            elif len(spec_pages) > 1 or len(html_slides) > 1:
                # Multi-page chapters need Agent-assisted report splits.
                if index > 0 or source != "chapter-fallback":
                    missing_report_mappings.append({
                        "unit_id": unit_id,
                        "chapter": chapter,
                        "reason": "同一报告章节对应多个页面；报告单元拆分需 Agent 根据 Spec 映射完成，预检不自动标为完成",
                    })

            if global_order == 0 and not role:
                role = "cover"
            register_candidate({
                "id": unit_id,
                "chapter": chapter,
                "role": role or "content",
                "source": source,
                "report_path": f"reports/{chapter_slug}.md" if report_exists else None,
                "spec_path": f"specs/{chapter_slug}.md" if spec_path.is_file() else None,
                "html_path": f"slides/chapters/{chapter_slug}.html" if html_path.is_file() else None,
                "spec_slide_number": spec_page["slide_number"] if spec_page else None,
                "html_index": index if html_slide else None,
            })

    if candidate_units:
        # Formal manifest rules (non-empty, unique IDs, cover first) must pass for can_migrate.
        formal_units = [
            Unit(id=unit["id"], chapter=unit["chapter"], role=unit["role"])
            for unit in candidate_units
        ]
        for error in validate_units(formal_units, chapters):
            if error not in conflicts:
                conflicts.append(error)

    # Deduplicate missing_report_mappings by unit_id+reason
    deduped: list[dict[str, str]] = []
    seen_missing: set[tuple[str, str]] = set()
    for item in missing_report_mappings:
        key = (item["unit_id"], item["reason"])
        if key in seen_missing:
            continue
        seen_missing.add(key)
        deduped.append(item)

    mapping_blockers = [item["unit_id"] for item in deduped]
    conflict_blockers = [
        unit["id"] for unit in candidate_units if any(unit["id"] in conflict for conflict in conflicts)
    ]
    blocked_units = list(dict.fromkeys(mapping_blockers + conflict_blockers))
    can_migrate = not conflicts and not deduped

    return {
        "dry_run": True,
        "preview_ok": True,
        "format_version": "v1",
        "target_format": "v2",
        "schema_version": SCHEMA_VERSION,
        "can_migrate": can_migrate,
        "candidate_units": candidate_units,
        "conflicts": conflicts,
        "warnings": warnings,
        "missing_report_mappings": deduped,
        "html_boundaries": html_boundaries,
        "selected_units": [unit["id"] for unit in candidate_units],
        "affected_units": [unit["id"] for unit in candidate_units],
        "reused_units": [],
        "blocked_units": blocked_units,
        "reasons": {
            **{item["unit_id"]: item["reason"] for item in deduped},
            **{f"conflict-{index}": conflict for index, conflict in enumerate(conflicts)},
        },
        "message": (
            "只读迁移预检完成；未修改项目文件。"
            + ("候选单元已通过可行性检查，可进入后续正式迁移。" if can_migrate
               else "存在冲突或待确认报告映射，尚不能标记为可迁移。")
        ),
    }


def _copy_tree(source: Path, destination: Path) -> None:
    import shutil

    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def migrate_to_units(base: Path, chapters: list[str]) -> dict[str, Any]:
    """Formal v1→v2 migration with backup + staging; leaves units pending review."""
    import shutil
    from datetime import datetime, timezone

    preview = migrate_to_units_preview(base, chapters)
    if preview.get("format_version") == "v2":
        return {
            **preview,
            "dry_run": False,
            "migrated": False,
            "message": "项目已是 v2，无需迁移",
        }
    if not preview.get("can_migrate"):
        raise UnitsError(
            "迁移预检未通过，拒绝正式迁移："
            + ("；".join(preview.get("conflicts") or []) or "存在待确认的报告映射")
            + "。请先运行 --dry-run 查看明细并完成人工/Agent 拆分。"
        )

    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    backup_root = base / ".state" / "migrate-backup" / stamp
    staging_root = base / ".state" / "migrate-staging" / stamp
    backup_root.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)

    # Backup chapter artifacts and approvals.
    for relative in ("reports", "specs", "slides/chapters", ".state/approvals.json", "slides/index.html"):
        source = base / relative
        if source.exists():
            _copy_tree(source, backup_root / relative)
    (backup_root / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": stamp,
                "chapters": chapters,
                "candidate_units": preview["candidate_units"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ensure_v2_directories(staging_root)
    units = [
        Unit(id=item["id"], chapter=item["chapter"], role=item["role"])
        for item in preview["candidate_units"]
    ]
    write_units_manifest(staging_root, units)

    # Materialize unit files into staging (1:1 chapter pages only when can_migrate).
    for item in preview["candidate_units"]:
        unit_id = item["id"]
        paths = unit_paths(staging_root, unit_id)
        paths.report.parent.mkdir(parents=True, exist_ok=True)
        paths.spec.parent.mkdir(parents=True, exist_ok=True)
        paths.page.parent.mkdir(parents=True, exist_ok=True)
        if item.get("report_path"):
            report_src = base / item["report_path"]
            if report_src.is_file():
                paths.report.write_bytes(report_src.read_bytes())
        if item.get("spec_path"):
            spec_src = base / item["spec_path"]
            if spec_src.is_file():
                # Extract the matching Slide page when possible.
                text = spec_src.read_text(encoding="utf-8")
                pages = list(SPEC_PAGE_RE.finditer(text))
                written = False
                for index, match in enumerate(pages):
                    end = pages[index + 1].start() if index + 1 < len(pages) else len(text)
                    page = text[match.start():end]
                    page_id = SPEC_PAGE_ID_RE.search(page)
                    if page_id and page_id.group(1) == unit_id:
                        paths.spec.write_text(page.strip() + "\n", encoding="utf-8")
                        written = True
                        break
                if not written:
                    paths.spec.write_text(text, encoding="utf-8")
        if item.get("html_path"):
            html_src = base / item["html_path"]
            if html_src.is_file():
                from .cli import SlideFragmentParser

                parser = SlideFragmentParser()
                parser.feed(html_src.read_text(encoding="utf-8"))
                parser.close()
                match_slide = None
                for slide in parser.slides:
                    if (slide.get("id") or "") == unit_id:
                        match_slide = slide
                        break
                if match_slide is None and len(parser.slides) == 1:
                    match_slide = parser.slides[0]
                if match_slide is None and item.get("html_index") is not None:
                    idx = int(item["html_index"])
                    if 0 <= idx < len(parser.slides):
                        match_slide = parser.slides[idx]
                if match_slide is None:
                    raise UnitsError(f"无法从 {item['html_path']} 定位单元 {unit_id} 的 HTML 片段")
                html_body = "".join(match_slide["html"])
                if "data-unit-id=" not in html_body:
                    html_body = html_body.replace(
                        'class="',
                        f'data-unit-id="{unit_id}" class="',
                        1,
                    )
                css = "".join(parser.css)
                if css:
                    html_body = f"<style>{css}</style>\n{html_body}"
                paths.page.write_text(html_body, encoding="utf-8")

    # Validate staging assemble / manifest before switching.
    loaded, load_errors = load_units_manifest(staging_root, chapters)
    if load_errors:
        raise UnitsError("暂存校验失败：" + "；".join(load_errors))
    document, assemble_errors = assemble_report(staging_root, loaded, write=True)
    if assemble_errors:
        raise UnitsError("暂存组装失败：" + "；".join(assemble_errors))

    # Switch: copy staging unit trees into live workspace and write units.json.
    ensure_v2_directories(base)
    for relative in ("reports/units", "specs/units", "slides/pages", "slides/previews", ".state/units"):
        live = base / relative
        staged = staging_root / relative
        if live.exists():
            shutil.rmtree(live)
        if staged.exists():
            shutil.copytree(staged, live)
    if (staging_root / "reports" / "report.md").is_file():
        (base / "reports" / "report.md").write_bytes((staging_root / "reports" / "report.md").read_bytes())
    write_units_manifest(base, loaded)

    # Invalidate legacy chapter approvals — units start pending review.
    approvals = base / ".state" / "approvals.json"
    if approvals.is_file():
        approvals.rename(backup_root / "approvals.json.migrated-aside")

    pointer = base / ".state" / "migrate-latest.json"
    pointer.write_text(
        json.dumps({"stamp": stamp, "backup": str(backup_root.relative_to(base)), "units": [u.id for u in loaded]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return {
        "dry_run": False,
        "migrated": True,
        "format_version": "v2",
        "backup": str(backup_root.relative_to(base)),
        "staging": str(staging_root.relative_to(base)),
        "units": [unit.id for unit in loaded],
        "assembled_report": bool(document),
        "message": (
            f"已迁移为 v2（{len(loaded)} 个单元）。备份：{backup_root.relative_to(base)}。"
            "新单元默认待审阅；可用 my-slides migrate --rollback 回滚到迁前备份。"
        ),
    }


def rollback_units_migration(base: Path, stamp: str | None = None) -> dict[str, Any]:
    """Restore the latest (or named) migrate backup and remove units.json."""
    import shutil

    pointer = base / ".state" / "migrate-latest.json"
    if stamp is None:
        if not pointer.is_file():
            raise UnitsError("没有可回滚的迁移记录（缺少 .state/migrate-latest.json）")
        stamp = json.loads(pointer.read_text(encoding="utf-8"))["stamp"]
    backup_root = base / ".state" / "migrate-backup" / stamp
    if not backup_root.is_dir():
        raise UnitsError(f"找不到迁移备份：.state/migrate-backup/{stamp}")

    # Remove v2 markers/trees then restore backup.
    units_path = units_manifest_path(base)
    if units_path.is_file():
        units_path.unlink()
    for relative in ("reports/units", "specs/units", "slides/pages", "slides/previews", ".state/units"):
        target = base / relative
        if target.exists():
            shutil.rmtree(target)
    for relative in ("reports", "specs", "slides/chapters"):
        src = backup_root / relative
        dst = base / relative
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    if (backup_root / "slides" / "index.html").is_file():
        (base / "slides").mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_root / "slides" / "index.html", base / "slides" / "index.html")
    for name in ("approvals.json", "approvals.json.migrated-aside"):
        src = backup_root / name
        if src.is_file():
            shutil.copy2(src, base / ".state" / "approvals.json")
            break
    if pointer.is_file():
        pointer.unlink()
    return {
        "rolled_back": True,
        "stamp": stamp,
        "format_version": detect_format_version(base),
        "message": f"已回滚到迁移备份 {stamp}；当前格式：{detect_format_version(base)}",
    }
