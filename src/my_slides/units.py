"""Unit-format schema, path helpers, validation, and report assembly.

v2 projects are identified by my-slides/units.json. Legacy chapter migration
is unsupported.
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
            "message": "当前为 v1 章节格式；旧版章节迁移已不支持，请重新 my-slides init 创建 v2 项目",
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
