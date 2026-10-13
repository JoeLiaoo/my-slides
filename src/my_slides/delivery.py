"""Offline delivery of v2 slide decks (issue #28 phase 4).

A delivery is a single offline ``index.html`` snapshot, copied under a
versioned file name (``<project>-v<N>-<date>.html``) and recorded in
``.state/deliveries.json`` so future runs can show the most recent delivery
and which units have changed since.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .dependencies import fingerprint_file
from .state import refresh_unit_currency
from .units import load_units_manifest, unit_paths


DELIVERY_FILENAME_RE = re.compile(
    r"^(?P<project>.+)-v(?P<sequence>\d+)-(?P<date>\d{4}-\d{2}-\d{2})\.html$"
)


def deliveries_path(base: Path) -> Path:
    return base / ".state" / "deliveries.json"


def delivery_index_path(base: Path) -> Path:
    return base / "slides" / "index.html"


def _normalize_date(date: datetime | str) -> str:
    if isinstance(date, str):
        return date
    return date.strftime("%Y-%m-%d")


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


def units_for_delivery(base: Path, chapters: list[str], project_root: Path) -> tuple[list, dict[str, dict[str, Any]]]:
    """Return units and per-unit fingerprints needed for delivery verification."""
    units, errors = load_units_manifest(base, chapters)
    if errors:
        raise ValueError("；".join(errors))
    if not units:
        raise ValueError("units.json 中没有单元；请先补充单元清单")
    states: dict[str, dict[str, Any]] = {}
    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        paths = unit_paths(base, unit.id)
        states[unit.id] = {
            "report_sha256": fingerprint_file(paths.report),
            "spec_sha256": fingerprint_file(paths.spec),
            "html_sha256": fingerprint_file(paths.page),
            "deck_sha256": fingerprint_file(delivery_index_path(base)) if delivery_index_path(base).is_file() else None,
            "state": state,
        }
    return units, states


def export_delivery(
    base: Path,
    cfg: dict[str, Any],
    *,
    project_root: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Verify current state, copy ``slides/index.html`` to a versioned file.

    Refuses when any unit's report, Spec, HTML, or browser check is not
    current. Records the new entry in ``.state/deliveries.json``.
    """
    chapters = [str(item) for item in cfg.get("chapters") or []]
    deck_path = delivery_index_path(base)
    if not deck_path.is_file():
        raise ValueError("slides/index.html 不存在；请先运行 my-slides slides build --all")
    units, states = units_for_delivery(base, chapters, project_root)

    blockers: list[str] = []
    pending: list[str] = []
    outdated: list[dict[str, str]] = []
    for unit in units:
        state = states[unit.id]["state"]
        if not state["report"]["current"]:
            if state["report"].get("pending_current"):
                pending.append(f"{unit.id}（报告待用户确认）")
            else:
                outdated.append({"unit": unit.id, "kind": "report", "reason": "报告未批准或已过期"})
        if not state["spec"]["current"]:
            if state["spec"].get("pending_current"):
                pending.append(f"{unit.id}（Spec 待用户确认）")
            else:
                outdated.append({"unit": unit.id, "kind": "spec", "reason": "Spec 未批准或已过期"})
        if not state["html"]["current"]:
            outdated.append({"unit": unit.id, "kind": "html", "reason": "HTML 未按当前 Spec 构建"})
        if not state["check"]["current"]:
            outdated.append({"unit": unit.id, "kind": "check", "reason": "页面检查结果已过期"})
    if pending or outdated:
        problems = [f"{item['unit']} {item['kind']}: {item['reason']}" for item in outdated]
        problems = pending + problems
        raise ValueError("交付前需要补齐：" + "；".join(problems))

    project_name = str(cfg.get("project") or project_root.name)
    safe_name = _safe_project_name(project_name)
    today = _normalize_date(datetime.now())
    records = _read_records(base)
    sequence = _sequence_for_date(records, today)
    filename = f"{safe_name}-v{sequence}-{today}.html"

    target_dir = (output_dir or project_root).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    delivered_at = datetime.now().isoformat(timespec="seconds")
    package_version = __version__
    units_payload = [
        {
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "report_sha256": states[unit.id]["report_sha256"],
            "spec_sha256": states[unit.id]["spec_sha256"],
            "html_sha256": states[unit.id]["html_sha256"],
            "report_approved_by": states[unit.id]["state"]["report"].get("approved_by"),
            "spec_approved_by": states[unit.id]["state"]["spec"].get("approved_by"),
        }
        for unit in units
    ]
    deck_sha = fingerprint_file(deck_path)

    target.write_bytes(deck_path.read_bytes())
    record = {
        "sequence": sequence,
        "date": today,
        "delivered_at": delivered_at,
        "package_version": package_version,
        "project": project_name,
        "file": filename,
        "path": str(target),
        "deck_sha256": deck_sha,
        "units": units_payload,
    }
    records.append(record)
    _write_records(base, records)
    return {
        "exported": True,
        "file": filename,
        "path": str(target),
        "sequence": sequence,
        "date": today,
        "delivered_at": delivered_at,
        "package_version": package_version,
        "deck_sha256": deck_sha,
        "units": units_payload,
    }


def units_changed_since(base: Path, project_root: Path) -> dict[str, Any]:
    """Summarize per-unit changes since the most recent delivery."""
    record = last_delivery(base)
    if record is None:
        return {
            "has_delivery": False,
            "changed_units": [],
            "unchanged_units": [],
            "missing_units": [],
        }
    deck_path = delivery_index_path(base)
    current_deck_sha = fingerprint_file(deck_path) if deck_path.is_file() else None
    by_id = {item["id"]: item for item in record.get("units", [])}
    from .units import detect_format_version

    if detect_format_version(base) != "v2":
        return {
            "has_delivery": True,
            "delivery": record,
            "changed_units": [],
            "unchanged_units": [],
            "missing_units": [],
            "deck_changed": current_deck_sha != record.get("deck_sha256"),
        }
    units, errors = load_units_manifest(base, chapters=None)
    if errors:
        raise ValueError("；".join(errors))
    changed: list[dict[str, str]] = []
    unchanged: list[str] = []
    missing: list[str] = []
    for unit in units:
        paths = unit_paths(base, unit.id)
        report_sha = fingerprint_file(paths.report)
        spec_sha = fingerprint_file(paths.spec)
        html_sha = fingerprint_file(paths.page)
        previous = by_id.get(unit.id)
        if previous is None:
            changed.append({"unit": unit.id, "reason": "新增单元，自上次交付后才加入"})
            continue
        differences: list[str] = []
        if previous.get("report_sha256") != report_sha:
            differences.append("报告正文")
        if previous.get("spec_sha256") != spec_sha:
            differences.append("Spec")
        if previous.get("html_sha256") != html_sha:
            differences.append("HTML 页面")
        if differences:
            changed.append({"unit": unit.id, "reason": "、".join(differences) + " 已变化"})
        else:
            unchanged.append(unit.id)
    for old_id in by_id:
        if old_id not in {unit.id for unit in units}:
            missing.append(old_id)
    return {
        "has_delivery": True,
        "delivery": record,
        "changed_units": changed,
        "unchanged_units": unchanged,
        "missing_units": missing,
        "deck_changed": current_deck_sha != record.get("deck_sha256"),
    }
