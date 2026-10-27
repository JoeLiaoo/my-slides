"""Per-unit report approval state for v2 projects.

Each unit stores `.state/units/<id>.json` with content fingerprints (not mtimes).
Invalidation follows real local + explicit unit dependencies (see dependencies.py).
Changing an unlinked Wiki page does **not** revoke approvals for unrelated units.

Slides are not tracked per unit: they live in the Design deck and are reviewed
by the user on the Design host, so only the report carries an approval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dependencies import (
    build_unit_dependency_graph,
    content_fingerprint,
    detect_unit_cycles,
    fingerprint_file,
    fingerprint_json,
    report_closure_fingerprints,
    units_affected_by_file,
)
from .units import Unit, UnitsError, load_units_manifest, unit_paths

APPROVAL_KINDS = ("report",)


def unit_state_path(base: Path, unit_id: str) -> Path:
    return unit_paths(base, unit_id).state


def require_approval_kind(kind: str) -> None:
    if kind not in APPROVAL_KINDS:
        raise ValueError(f"未知审批类型：{kind}")


def default_unit_state(unit_id: str) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "report": {
            "content_sha256": None,
            "input_fingerprint": None,
            "approved_input_fingerprint": None,
            "approved_sha256": None,
            "approved_at": None,
            "approved_by": None,
            "approved_account": None,
            "pending_approval": None,
            "pending_current": False,
            "reconfirmation_required": False,
            "reconfirmation_context": None,
            "approval_channel": None,
            "user_reply": None,
            "latest_decision": None,
            "latest_rejection": None,
            "decision_history": [],
            "current": False,
        },
        "reasons": [],
    }


def read_unit_state(base: Path, unit_id: str) -> dict[str, Any]:
    """Read a unit state; fields from the retired Spec/HTML pipeline are dropped."""
    path = unit_state_path(base, unit_id)
    if not path.is_file():
        return default_unit_state(unit_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnitsError(f"单元状态损坏：{path.name}（{exc}）") from exc
    if not isinstance(data, dict):
        raise UnitsError(f"单元状态必须是对象：{path.name}")
    merged = default_unit_state(unit_id)
    if isinstance(data.get("report"), dict):
        merged["report"].update(data["report"])
    if isinstance(data.get("reasons"), list):
        merged["reasons"] = [str(item) for item in data["reasons"]]
    if isinstance(data.get("identity_migrations"), list):
        merged["identity_migrations"] = data["identity_migrations"]
    bucket = merged["report"]
    if not isinstance(bucket.get("decision_history"), list):
        bucket["decision_history"] = []
    if bucket.get("latest_decision") not in {None, "approved", "rejected"}:
        bucket["latest_decision"] = None
    if bucket.get("latest_rejection") is not None and not isinstance(bucket["latest_rejection"], dict):
        bucket["latest_rejection"] = None
    return merged


def write_unit_state(base: Path, unit_id: str, state: dict[str, Any]) -> Path:
    path = unit_state_path(base, unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return path


def compute_report_input_fingerprint(base: Path, unit: Unit, project_root: Path | None = None) -> str:
    closure = report_closure_fingerprints(base, unit, project_root=project_root)
    return fingerprint_json(
        {
            "report_sha256": closure["report_sha256"],
            "local_files": closure["local_files"],
            "depends_on_units": closure["depends_on_units"],
        }
    )


def refresh_unit_currency(base: Path, unit: Unit, *, project_root: Path | None = None) -> dict[str, Any]:
    """Recompute current flags from on-disk content vs stored approvals."""
    state = read_unit_state(base, unit.id)
    paths = unit_paths(base, unit.id)
    reasons: list[str] = []

    report_sha = fingerprint_file(paths.report)
    input_fp = compute_report_input_fingerprint(base, unit, project_root=project_root) if paths.report.is_file() else None
    # 当前指纹和批准时指纹必须分开保存。先写入再和自己比较会让依赖检查永远通过。
    approved_input = state["report"].get("approved_input_fingerprint")
    state["report"]["content_sha256"] = report_sha
    state["report"]["input_fingerprint"] = input_fp
    approved = state["report"].get("approved_sha256")
    reconfirmation_required = bool(state["report"].get("reconfirmation_required"))
    report_current = bool(
        approved
        and report_sha
        and approved == report_sha
        and approved_input
        and approved_input == input_fp
        and state["report"].get("approved_by")
        and state["report"].get("approved_account")
        and not reconfirmation_required
    )
    if approved and not report_current:
        if not state["report"].get("approved_by") or not state["report"].get("approved_account"):
            reasons.append("报告旧批准缺少审阅者记录，需重新审阅")
        elif reconfirmation_required and state["report"].get("reconfirmation_context"):
            reasons.append("章节变更待用户重新确认：" + str(state["report"]["reconfirmation_context"]))
        else:
            reasons.append("报告内容或本地依赖已变化，需重新审阅")
    state["report"]["current"] = report_current
    report_request = state["report"].get("pending_approval")
    state["report"]["pending_current"] = bool(
        isinstance(report_request, dict)
        and report_request.get("content_sha256") == report_sha
        and report_request.get("input_fingerprint") == input_fp
    )
    state["reasons"] = reasons
    return state


def collect_units_status(
    base: Path,
    *,
    selected: list[str] | None = None,
    chapters: list[str] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Per-unit report status plus the Design pages each unit owns."""
    from .design_deck import unit_pages

    units, errors = load_units_manifest(base, chapters)
    if errors:
        raise UnitsError("；".join(errors))
    graph = build_unit_dependency_graph(base, units)
    cycle_errors = detect_unit_cycles(graph)
    if cycle_errors:
        raise UnitsError("；".join(cycle_errors))

    by_id = {unit.id: unit for unit in units}
    if selected:
        missing = [unit_id for unit_id in selected if unit_id not in by_id]
        if missing:
            raise UnitsError("未知单元：" + "、".join(missing))
        chosen = [by_id[unit_id] for unit_id in selected]
    else:
        chosen = list(units)

    unit_rows: list[dict[str, Any]] = []
    affected: list[str] = []
    reused: list[str] = []
    blocked: list[str] = []
    reasons: dict[str, list[str]] = {}

    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        write_unit_state(base, unit.id, state)
        report = state["report"]
        row = {
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "role": unit.role,
            "report_current": report["current"],
            "report_pending": report["pending_current"],
            "report_reconfirmation_context": report.get("reconfirmation_context"),
            "report_approved_by": report.get("approved_by"),
            "report_approved_account": report.get("approved_account"),
            "report_approved_at": report.get("approved_at"),
            "report_approval_channel": report.get("approval_channel"),
            "report_user_reply": report.get("user_reply"),
            "report_unattributed": bool(report.get("approved_sha256"))
            and (not report.get("approved_by") or not report.get("approved_account")),
            "report_latest_decision": report.get("latest_decision"),
            "report_latest_rejection": report.get("latest_rejection"),
            "pages": unit_pages(base, unit.id),
            "reasons": state["reasons"],
            "depends_on": graph.get(unit.id, []),
        }
        unit_rows.append(row)
        if unit in chosen:
            if state["reasons"]:
                affected.append(unit.id)
                reasons[unit.id] = list(state["reasons"])
            elif not unit_paths(base, unit.id).report.is_file():
                blocked.append(unit.id)
                reasons[unit.id] = ["缺少报告单元文件"]
            else:
                reused.append(unit.id)

    return {
        "format_version": "v2",
        "selected_units": [unit.id for unit in chosen],
        "affected_units": affected,
        "reused_units": reused,
        "blocked_units": blocked,
        "reasons": reasons,
        "units": unit_rows,
        "dependency_graph": graph,
    }


def mark_report_approved(
    base: Path,
    unit: Unit,
    *,
    project_root: Path | None = None,
    when: str,
    approved_by: str | None = None,
    approved_account: str | None = None,
    channel: str | None = None,
    user_reply: str | None = None,
) -> dict[str, Any]:
    state = refresh_unit_currency(base, unit, project_root=project_root)
    paths = unit_paths(base, unit.id)
    if not paths.report.is_file():
        raise UnitsError(f"缺少报告单元：{unit.id}")
    sha = fingerprint_file(paths.report)
    input_fp = compute_report_input_fingerprint(base, unit, project_root=project_root)
    prior_history = list(state["report"].get("decision_history") or [])
    prior_history.append({
        "decision": "approved",
        "approved_by": approved_by,
        "approved_account": approved_account,
        "approved_at": when,
        "channel": channel,
        "user_reply": user_reply,
        "approved_sha256": sha,
    })
    state["report"] = {
        "content_sha256": sha,
        "input_fingerprint": input_fp,
        "approved_input_fingerprint": input_fp,
        "approved_sha256": sha,
        "approved_at": when,
        "approved_by": approved_by,
        "approved_account": approved_account,
        "pending_approval": None,
        "pending_current": False,
        "reconfirmation_required": False,
        "reconfirmation_context": None,
        "approval_channel": channel,
        "user_reply": user_reply,
        "latest_decision": "approved",
        "latest_rejection": state["report"].get("latest_rejection"),
        "decision_history": prior_history,
        "current": bool(approved_by and approved_account),
    }
    state["reasons"] = []
    write_unit_state(base, unit.id, state)
    return state


def invalidate_for_changed_file(
    base: Path,
    changed: Path,
    *,
    chapters: list[str] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    units, errors = load_units_manifest(base, chapters)
    if errors:
        raise UnitsError("；".join(errors))
    impact = units_affected_by_file(base, units, changed, project_root=project_root)
    for unit_id in impact["affected_units"]:
        unit = next(u for u in units if u.id == unit_id)
        state = refresh_unit_currency(base, unit, project_root=project_root)
        reason = impact["reasons"].get(unit_id, "依赖变化")
        if reason not in state["reasons"]:
            state["reasons"].append(reason)
        state["report"]["current"] = False
        write_unit_state(base, unit.id, state)
    return impact


def record_rejection(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    project_root: Path | None = None,
    when: str,
    reason: str,
    rejected_by: str,
    rejected_account: str,
    channel: str,
    user_reply: str | None = None,
    clear_pending: bool = True,
) -> dict[str, Any]:
    """Record a user rejection of a pending request.

    Keeps the rejection in history; clears only the pending request. The
    rejection does **not** invalidate an existing approval: only the pending
    new version is declined. ``refresh_unit_currency`` then decides whether
    the current approval is still valid against the on-disk files.
    """
    require_approval_kind(kind)
    state = refresh_unit_currency(base, unit, project_root=project_root)
    bucket = state[kind]
    if not reason or not str(reason).strip():
        raise ValueError("驳回原因不能为空")
    rejection_entry = {
        "reason": str(reason).strip(),
        "rejected_by": rejected_by,
        "rejected_account": rejected_account,
        "rejected_at": when,
        "channel": channel,
        "user_reply": user_reply,
    }
    history = list(bucket.get("decision_history") or [])
    history.append({"decision": "rejected", **rejection_entry})
    bucket["latest_decision"] = "rejected"
    bucket["latest_rejection"] = rejection_entry
    bucket["decision_history"] = history
    if clear_pending:
        bucket["pending_approval"] = None
        bucket["pending_current"] = False
    reasons = list(state.get("reasons") or [])
    message = f"用户驳回了报告：{rejection_entry['reason']}"
    if message not in reasons:
        reasons.append(message)
    state["reasons"] = reasons
    write_unit_state(base, unit.id, state)
    return state


def revoke_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    project_root: Path | None = None,
    when: str,
    reason: str | None = None,
    revoked_by: str,
    revoked_account: str,
    channel: str,
    user_reply: str | None = None,
) -> dict[str, Any]:
    """Drop a current approval.

    Approved copies in ``.state/approved/`` are preserved so previous versions
    stay in history.
    """
    require_approval_kind(kind)
    state = refresh_unit_currency(base, unit, project_root=project_root)
    bucket = state[kind]
    if not bucket.get("approved_sha256"):
        raise UnitsError(f"{unit.id}：{kind} 还没有有效的批准；无需撤回")
    history = list(bucket.get("decision_history") or [])
    history.append({
        "decision": "revoked",
        "reason": (reason or "").strip() or None,
        "revoked_by": revoked_by,
        "revoked_account": revoked_account,
        "revoked_at": when,
        "channel": channel,
        "user_reply": user_reply,
        "previously_approved_sha256": bucket.get("approved_sha256"),
        "previously_approved_at": bucket.get("approved_at"),
    })
    bucket.update({
        "approved_sha256": None,
        "approved_input_fingerprint": None,
        "approved_at": None,
        "approved_by": None,
        "approved_account": None,
        "approval_channel": None,
        "user_reply": None,
        "current": False,
        "reconfirmation_required": False,
        "reconfirmation_context": None,
        "pending_approval": None,
        "pending_current": False,
        "latest_decision": "rejected",
        "latest_rejection": {
            "reason": (reason or "").strip() or "用户撤回了批准",
            "rejected_by": revoked_by,
            "rejected_account": revoked_account,
            "rejected_at": when,
            "channel": channel,
            "user_reply": user_reply,
        },
        "decision_history": history,
    })
    reasons = list(state.get("reasons") or [])
    note = "用户撤回了报告批准"
    if reason:
        note += f"：{str(reason).strip()}"
    if note not in reasons:
        reasons.append(note)
    state["reasons"] = reasons
    write_unit_state(base, unit.id, state)
    return state


def withdraw_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    project_root: Path | None = None,
    when: str,
) -> dict[str, Any]:
    """Agent cancels its own pending approval request; no user gate required."""
    require_approval_kind(kind)
    state = refresh_unit_currency(base, unit, project_root=project_root)
    bucket = state[kind]
    if not bucket.get("pending_approval"):
        raise UnitsError(f"{unit.id}：{kind} 没有待审申请；无需撤回")
    history = list(bucket.get("decision_history") or [])
    history.append({
        "decision": "withdrawn",
        "withdrawn_at": when,
        "previously_requested_at": bucket["pending_approval"].get("requested_at"),
    })
    bucket["pending_approval"] = None
    bucket["pending_current"] = False
    bucket["decision_history"] = history
    # A withdrawal is not a user decision; it never becomes latest_decision.
    write_unit_state(base, unit.id, state)
    return state


# Re-export fingerprint helpers for tests / callers.
__all__ = [
    "APPROVAL_KINDS",
    "collect_units_status",
    "compute_report_input_fingerprint",
    "content_fingerprint",
    "default_unit_state",
    "fingerprint_file",
    "fingerprint_json",
    "invalidate_for_changed_file",
    "mark_report_approved",
    "read_unit_state",
    "record_rejection",
    "refresh_unit_currency",
    "require_approval_kind",
    "revoke_approval",
    "unit_state_path",
    "withdraw_approval",
    "write_unit_state",
]
