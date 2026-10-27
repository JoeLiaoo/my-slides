"""Offline delivery of the Design deck (issue #28 phase 4, issue #58).

A delivery is one offline HTML exported by the running Design host under a
versioned file name (``<project>-v<N>-<date>.html``) and recorded in
``.state/deliveries.json`` with per-unit report and page hashes, so later runs
can show the most recent delivery and which units changed since.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .dependencies import fingerprint_file
from .design_deck import DECK_NAME, deck_dir, deck_fingerprint, projects_root, unapproved_reports, unit_pages
from .design_engine import DEFAULT_BASE_URL, host_command, run_agent
from .design_workflow import mapping_errors
from .state import refresh_unit_currency
from .units import load_units_manifest, unit_paths


DELIVERY_FILENAME_RE = re.compile(
    r"^(?P<project>.+)-v(?P<sequence>\d+)-(?P<date>\d{4}-\d{2}-\d{2})\.html$"
)


def deliveries_path(base: Path) -> Path:
    return base / ".state" / "deliveries.json"


def _sequence_for_date(records: list[dict[str, Any]], date: str) -> int:
    sequences = [
        int(record.get("sequence"))
        for record in records
        if record.get("date") == date and isinstance(record.get("sequence"), int)
    ]
    return max(sequences, default=0) + 1


def _safe_project_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", name.strip()).strip("-")
    return cleaned or "project"


def _read_records(base: Path) -> list[dict[str, Any]]:
    path = deliveries_path(base)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    records = payload.get("deliveries")
    return records if isinstance(records, list) else []


def _write_records(base: Path, records: list[dict[str, Any]]) -> None:
    path = deliveries_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "format_version": "v2",
        "package_version": __version__,
        "deliveries": records,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def list_deliveries(base: Path) -> list[dict[str, Any]]:
    return _read_records(base)


def last_delivery(base: Path) -> dict[str, Any] | None:
    records = _read_records(base)
    if not records:
        return None
    return sorted(records, key=lambda item: (str(item.get("delivered_at", "")), int(item.get("sequence", 0))))[-1]


def _page_hashes(base: Path, unit_id: str) -> dict[str, str | None]:
    return {page: fingerprint_file(deck_dir(base) / "slides" / f"{page}.html") for page in unit_pages(base, unit_id)}


def export_delivery(
    base: Path,
    cfg: dict[str, Any],
    *,
    project_root: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Export the deck as one offline HTML through the running host and record the delivery.

    Refuses when a unit report lacks a current approval or a unit has no page.
    The Design export itself re-runs the structure check before writing.
    """
    if deck_fingerprint(base) is None:
        raise ValueError("Design deck 尚未创建：请先运行 my-slides slides build --all")
    units, errors = mapping_errors(base, cfg)
    blocked = unapproved_reports(base, units)
    if blocked:
        errors.insert(0, "报告未获得当前有效批准：" + "、".join(blocked))
    if errors:
        raise ValueError("交付前需要补齐：" + "；".join(errors))
    project_name = str(cfg.get("project") or project_root.name)
    today = datetime.now().strftime("%Y-%m-%d")
    records = _read_records(base)
    sequence = _sequence_for_date(records, today)
    filename = f"{_safe_project_name(project_name)}-v{sequence}-{today}.html"
    target_dir = (output_dir or project_root).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    code, exported = run_agent(["export", DECK_NAME, "--format", "html", "--out", str(target)],
                               projects_root(base), base_url=DEFAULT_BASE_URL)
    if code or not exported.get("ok"):
        raise ValueError(f"Design 导出失败：{exported.get('code')} {exported.get('message', '')}".strip()
                         + f"。导出需要宿主在运行：{host_command(projects_root(base))}")
    units_payload = []
    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        units_payload.append({
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "report_sha256": fingerprint_file(unit_paths(base, unit.id).report),
            "report_approved_by": state["report"].get("approved_by"),
            "pages": _page_hashes(base, unit.id),
        })
    record = {
        "sequence": sequence,
        "date": today,
        "delivered_at": datetime.now().isoformat(timespec="seconds"),
        "package_version": __version__,
        "project": project_name,
        "presentation": "design",
        "file": filename,
        "path": str(target),
        "deck_sha256": fingerprint_file(target),
        "deck_fingerprint": deck_fingerprint(base),
        "design_source_version": exported.get("sourceVersion"),
        "units": units_payload,
    }
    records.append(record)
    _write_records(base, records)
    return {"exported": True, **record}


def units_changed_since(base: Path, project_root: Path) -> dict[str, Any]:
    """Summarize per-unit report and page changes since the most recent delivery."""
    record = last_delivery(base)
    if record is None:
        return {
            "has_delivery": False,
            "changed_units": [],
            "unchanged_units": [],
            "missing_units": [],
        }
    units, errors = load_units_manifest(base, chapters=None)
    if errors:
        raise ValueError("；".join(errors))
    by_id = {item["id"]: item for item in record.get("units", [])}
    changed: list[dict[str, str]] = []
    unchanged: list[str] = []
    for unit in units:
        previous = by_id.get(unit.id)
        if previous is None:
            changed.append({"unit": unit.id, "reason": "新增单元，自上次交付后才加入"})
            continue
        differences: list[str] = []
        if previous.get("report_sha256") != fingerprint_file(unit_paths(base, unit.id).report):
            differences.append("报告正文")
        # 旧版 HTML 交付没有 pages 字段：视为页面已变化，提醒重新交付。
        if previous.get("pages") != _page_hashes(base, unit.id):
            differences.append("Design 页面")
        if differences:
            changed.append({"unit": unit.id, "reason": "、".join(differences) + " 已变化"})
        else:
            unchanged.append(unit.id)
    current_ids = {unit.id for unit in units}
    return {
        "has_delivery": True,
        "delivery": record,
        "changed_units": changed,
        "unchanged_units": unchanged,
        "missing_units": [old_id for old_id in by_id if old_id not in current_ids],
        "deck_changed": record.get("deck_fingerprint") != deck_fingerprint(base),
    }
