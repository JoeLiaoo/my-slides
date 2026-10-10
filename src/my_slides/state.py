"""Per-unit approval / build / check state for v2 projects.

Each unit stores `.state/units/<id>.json` with content fingerprints (not mtimes).
Invalidation follows real local + explicit unit dependencies (see dependencies.py).
Changing an unlinked Wiki page does **not** revoke approvals for unrelated units.
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


def unit_state_path(base: Path, unit_id: str) -> Path:
    return unit_paths(base, unit_id).state


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
            "current": False,
        },
        "spec": {
            "content_sha256": None,
            "report_sha256": None,
            "report_input_fingerprint": None,
            "approved_sha256": None,
            "approved_at": None,
            "approved_by": None,
            "approved_account": None,
            "pending_approval": None,
            "pending_current": False,
            "approval_channel": None,
            "user_reply": None,
            "current": False,
        },
        "html": {
            "content_sha256": None,
            "spec_sha256": None,
            "build_sha256": None,
            "current": False,
        },
        "check": {
            "input_fingerprint": None,
            "result": None,
            "current": False,
        },
        "reasons": [],
    }


def read_unit_state(base: Path, unit_id: str) -> dict[str, Any]:
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
    for key in ("report", "spec", "html", "check"):
        if isinstance(data.get(key), dict):
            merged[key].update(data[key])
    if isinstance(data.get("reasons"), list):
        merged["reasons"] = [str(item) for item in data["reasons"]]
    if isinstance(data.get("identity_migrations"), list):
        merged["identity_migrations"] = data["identity_migrations"]
    return merged


def write_unit_state(base: Path, unit_id: str, state: dict[str, Any]) -> Path:
    path = unit_state_path(base, unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return path


def check_input_fingerprint(
    html_sha: str | None,
    spec_sha: str | None,
    *,
    deck_sha: str | None = None,
) -> str:
    """Browser check currency uses this exact shape when saving and when refreshing.

    ``html`` is the built page version that was measured (build_sha256), not a
    possibly-edited live source file. ``deck`` is the formal index.html that
    check_deck actually opened.
    """
    payload: dict[str, str | None] = {"html": html_sha, "spec": spec_sha}
    if deck_sha is not None:
        payload["deck"] = deck_sha
    return fingerprint_json(payload)


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
    # A chapter-only move explicitly asks for a context reconfirmation, while an
    # unchanged report remains a valid binding for its already approved Spec.
    unchanged_reconfirmation = bool(
        reconfirmation_required
        and approved
        and report_sha == approved
        and approved_input
        and approved_input == input_fp
        and state["report"].get("approved_by")
        and state["report"].get("approved_account")
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

    spec_sha = fingerprint_file(paths.spec)
    state["spec"]["content_sha256"] = spec_sha
    bound_report = state["spec"].get("report_sha256")
    # Spec 必须绑到批准时的依赖版本；只比报告正文哈希会在依赖变后重批正文时误复活旧 Spec。
    bound_report_input = state["spec"].get("report_input_fingerprint")
    spec_approved = state["spec"].get("approved_sha256")
    spec_current = bool(
        spec_approved
        and spec_sha
        and spec_approved == spec_sha
        and (report_current or unchanged_reconfirmation)
        and bound_report
        and bound_report == approved
        and bound_report_input
        and bound_report_input == approved_input
        and state["spec"].get("approved_by")
        and state["spec"].get("approved_account")
    )
    if spec_approved and not spec_current:
        if not state["spec"].get("approved_by") or not state["spec"].get("approved_account"):
            reasons.append("Spec 旧批准缺少审阅者记录，需重新审阅")
        else:
            reasons.append("Spec 与已批准报告版本不一致或 Spec 已改动")
    state["spec"]["current"] = spec_current
    spec_request = state["spec"].get("pending_approval")
    state["spec"]["pending_current"] = bool(
        isinstance(spec_request, dict)
        and spec_request.get("content_sha256") == spec_sha
        and report_current
        and spec_request.get("report_sha256") == approved
        and spec_request.get("report_input_fingerprint") == approved_input
    )

    html_sha = fingerprint_file(paths.page)
    state["html"]["content_sha256"] = html_sha
    build_sha = state["html"].get("build_sha256")
    from .theme import shell_fingerprint

    # 主题或外壳变了只让 HTML 和检查过期，不撤销报告和 Spec 的批准。
    shell_ok = state["html"].get("shell_fingerprint") == shell_fingerprint()
    content_ok = bool(
        build_sha
        and html_sha
        and build_sha == html_sha
        and spec_current
        and state["html"].get("spec_sha256") == spec_approved
    )
    html_current = bool(content_ok and shell_ok)
    if build_sha and not content_ok:
        reasons.append("HTML 片段或绑定 Spec 已变化")
    elif build_sha and not shell_ok:
        reasons.append("幻灯片主题或外壳已变化，需重新构建")
    state["html"]["current"] = html_current

    deck_path = base / "slides" / "index.html"
    deck_sha = fingerprint_file(deck_path) if deck_path.is_file() else None
    check_current = bool(
        state["check"].get("result") == "pass"
        and state["check"].get("input_fingerprint")
        and deck_sha
        and build_sha
        and state["check"]["input_fingerprint"]
        == check_input_fingerprint(build_sha, spec_sha, deck_sha=deck_sha)
        and html_current
    )
    if state["check"].get("result") and not check_current:
        reasons.append("页面检查结果已过期")
    state["check"]["current"] = check_current
    state["reasons"] = reasons
    return state


def collect_units_status(
    base: Path,
    *,
    selected: list[str] | None = None,
    chapters: list[str] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Skeleton for `status --unit … --json` (human copy filled in Phase 4)."""
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
        row = {
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "role": unit.role,
            "report_current": state["report"]["current"],
            "report_pending": state["report"]["pending_current"],
            "report_reconfirmation_context": state["report"].get("reconfirmation_context"),
            "report_approved_by": state["report"].get("approved_by"),
            "report_approved_account": state["report"].get("approved_account"),
            "report_approved_at": state["report"].get("approved_at"),
            "report_approval_channel": state["report"].get("approval_channel"),
            "report_user_reply": state["report"].get("user_reply"),
            "report_unattributed": bool(state["report"].get("approved_sha256"))
            and (not state["report"].get("approved_by") or not state["report"].get("approved_account")),
            "spec_current": state["spec"]["current"],
            "spec_pending": state["spec"]["pending_current"],
            "spec_approved_by": state["spec"].get("approved_by"),
            "spec_approved_account": state["spec"].get("approved_account"),
            "spec_approved_at": state["spec"].get("approved_at"),
            "spec_approval_channel": state["spec"].get("approval_channel"),
            "spec_user_reply": state["spec"].get("user_reply"),
            "spec_unattributed": bool(state["spec"].get("approved_sha256"))
            and (not state["spec"].get("approved_by") or not state["spec"].get("approved_account")),
            "html_current": state["html"]["current"],
            "check_current": state["check"]["current"],
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
    prior_sha = state["report"].get("approved_sha256")
    prior_input = state["report"].get("approved_input_fingerprint")
    report_changed = prior_sha != sha or prior_input != input_fp
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
        "current": bool(approved_by and approved_account),
    }
    # A context-only reconfirmation keeps a Spec bound to the identical report.
    # Substantive report or dependency changes still require a new Spec approval.
    if report_changed and state["spec"].get("approved_sha256"):
        state["spec"]["current"] = False
        state["reasons"] = ["报告已重新批准，Spec 需按新报告版本更新后重审"]
        state["spec"]["pending_approval"] = None
        state["spec"]["pending_current"] = False
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
        state["spec"]["current"] = False
        state["html"]["current"] = False
        state["check"]["current"] = False
        write_unit_state(base, unit.id, state)
    return impact


# Re-export fingerprint helpers for tests / callers.
__all__ = [
    "check_input_fingerprint",
    "collect_units_status",
    "compute_report_input_fingerprint",
    "content_fingerprint",
    "default_unit_state",
    "fingerprint_file",
    "fingerprint_json",
    "invalidate_for_changed_file",
    "mark_report_approved",
    "read_unit_state",
    "refresh_unit_currency",
    "unit_state_path",
    "write_unit_state",
]
