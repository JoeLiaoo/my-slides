"""Per-unit prepare, validation, and approval for v2 projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import (
    collect_units_status,
    mark_report_approved,
    refresh_unit_currency,
    require_approval_kind,
    write_unit_state,
)
from .units import (
    Unit,
    UnitsError,
    assemble_report,
    ensure_v2_directories,
    load_units_manifest,
    unit_paths,
    validate_local_markdown_links,
)


def resolve_unit_selection(
    base: Path,
    cfg: dict[str, Any],
    *,
    unit_ids: list[str] | None,
    changed: bool,
    all_units: bool,
    chapter: str | None = None,
) -> list[Unit]:
    flags = sum(bool(x) for x in (unit_ids, changed, all_units, chapter))
    if flags > 1:
        raise ValueError("--unit、--changed、--all、--chapter 只能选一个")
    units, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        raise UnitsError("；".join(errors))
    if not units:
        raise UnitsError("units.json 中没有单元")
    by_id = {unit.id: unit for unit in units}
    if chapter:
        chosen = [unit for unit in units if unit.chapter == chapter]
        if not chosen:
            raise UnitsError(f"章节中没有小章节：{chapter}")
        return chosen
    if all_units or (not unit_ids and not changed):
        if not all_units and not unit_ids and not changed:
            raise ValueError("v2 项目请指定 --unit <id>、--changed、--all 或 --chapter")
        return list(units)
    if changed:
        status = collect_units_status(base, chapters=cfg.get("chapters"), project_root=base.parent)
        selected = list(dict.fromkeys(status["affected_units"] + status["blocked_units"]))
        if not selected:
            return []
        return [by_id[unit_id] for unit_id in selected]
    missing = [unit_id for unit_id in unit_ids or [] if unit_id not in by_id]
    if missing:
        raise UnitsError("未知单元：" + "、".join(missing))
    return [by_id[unit_id] for unit_id in unit_ids or []]


def validate_unit_report(base: Path, unit: Unit) -> list[str]:
    path = unit_paths(base, unit.id).report
    errors: list[str] = []
    if not path.is_file():
        return [f"缺少报告单元：reports/units/{unit.id}.md"]
    text = path.read_text(encoding="utf-8").strip()
    if len(text) < 30:
        errors.append(f"{unit.id}：报告内容过短")
    errors.extend(f"{unit.id}：{msg}" for msg in validate_local_markdown_links(text, path))
    return errors


def prepare_report_handoff(base: Path, root: Path, units: list[Unit]) -> list[Path]:
    """Write work/report/<id>.md telling the agent which report unit to write."""
    ensure_v2_directories(base)
    outputs: list[Path] = []
    for unit in units:
        output = base / "work" / "report" / f"{unit.id}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join([
            f"# report 单元交接：{unit.id}",
            "",
            f"项目目录：{root}",
            f"工作区：{base}",
            "规则：只改本单元对应的 reports/units 文件；不要编辑组装产物 reports/report.md（由 CLI 组装）。",
            "",
            f"## {unit.title or unit.id}",
            f"- 单元 ID：{unit.id}",
            f"- 大章节：{unit.chapter}",
            f"- 小章节：{unit.title or '（未命名）'}",
            f"- 角色：{unit.role}",
            f"- 报告：{unit_paths(base, unit.id).report.relative_to(base).as_posix()}",
            "",
            "请撰写完整论证、证据与限定条件，并用普通 Markdown 链接引用 Wiki/资料。",
            "",
        ]), encoding="utf-8")
        outputs.append(output)
    return outputs


def approve_unit_report(
    base: Path,
    unit: Unit,
    *,
    when: str,
    project_root: Path | None = None,
    approved_by: str | None = None,
    approved_account: str | None = None,
    channel: str | None = None,
    user_reply: str | None = None,
) -> dict[str, Any]:
    errors = validate_unit_report(base, unit)
    if errors:
        raise UnitsError("；".join(errors))
    state = mark_report_approved(
        base, unit, project_root=project_root or base.parent, when=when,
        approved_by=approved_by, approved_account=approved_account,
        channel=channel, user_reply=user_reply,
    )
    # Keep assembled report in sync after successful unit approve batches (caller may assemble).
    return state


def request_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Record exactly which report version awaits human review."""
    require_approval_kind(kind)
    errors = validate_unit_report(base, unit)
    if errors:
        raise UnitsError("；".join(errors))
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    request = {
        "requested_at": when,
        "content_sha256": state[kind]["content_sha256"],
        "input_fingerprint": state[kind]["input_fingerprint"],
    }
    state[kind]["pending_approval"] = request
    state[kind]["pending_current"] = True
    # Reset latest_decision so a re-submission after rejection no longer looks
    # rejected while the new request is still pending. The original rejection
    # stays in ``decision_history`` and ``latest_rejection`` for traceability.
    state[kind]["latest_decision"] = None
    write_unit_state(base, unit.id, state)
    return request


def confirm_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    approved_by: str,
    approved_account: str,
    project_root: Path | None = None,
    channel: str | None = None,
    user_reply: str | None = None,
) -> dict[str, Any]:
    """Apply a current review request after terminal or chat confirmation."""
    require_approval_kind(kind)
    if not approved_by.strip() or not approved_account.strip():
        raise ValueError("审批人和本机账户不能为空")
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    if not state[kind]["pending_current"]:
        raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请，或申请后内容/依赖已变化；请重新运行 approve {kind} --unit {unit.id}")
    state = approve_unit_report(
        base, unit, when=when, project_root=project_root,
        approved_by=approved_by.strip(), approved_account=approved_account.strip(),
        channel=channel, user_reply=user_reply,
    )
    from .approval_review import archive_approved_copy

    path = unit_paths(base, unit.id).report
    approved_sha = state[kind].get("approved_sha256")
    if isinstance(approved_sha, str) and approved_sha and path.is_file():
        archive_approved_copy(base, kind, unit.id, approved_sha, path.read_text(encoding="utf-8"))
    return state


def reject_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    reason: str,
    rejected_by: str,
    rejected_account: str,
    project_root: Path | None = None,
    channel: str | None = None,
    user_reply: str | None = None,
) -> dict[str, Any]:
    """Record a user rejection for a pending request."""
    from .state import record_rejection

    require_approval_kind(kind)
    if not rejected_by.strip() or not rejected_account.strip():
        raise ValueError("驳回人和本机账户不能为空")
    if not (reason or "").strip():
        raise ValueError("驳回原因不能为空")
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    if not state[kind]["pending_current"]:
        raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请，或申请后内容/依赖已变化；请重新运行 approve {kind} --unit {unit.id}")
    return record_rejection(
        base, unit, kind,
        project_root=project_root or base.parent, when=when, reason=reason.strip(),
        rejected_by=rejected_by.strip(), rejected_account=rejected_account.strip(),
        channel=channel, user_reply=user_reply,
        clear_pending=True,
    )


def withdraw_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Cancel a pending approval request the agent itself submitted."""
    from .state import withdraw_approval

    require_approval_kind(kind)
    return withdraw_approval(
        base, unit, kind, project_root=project_root or base.parent, when=when,
    )


def revoke_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    revoked_by: str,
    revoked_account: str,
    project_root: Path | None = None,
    channel: str | None = None,
    user_reply: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Drop a current approval; preserve approved copies and invalidate dependents."""
    from .state import revoke_approval

    require_approval_kind(kind)
    if not revoked_by.strip() or not revoked_account.strip():
        raise ValueError("撤回人和本机账户不能为空")
    return revoke_approval(
        base, unit, kind,
        project_root=project_root or base.parent, when=when,
        reason=reason, revoked_by=revoked_by.strip(),
        revoked_account=revoked_account.strip(),
        channel=channel, user_reply=user_reply,
    )


def assemble_after_report_approvals(
    base: Path,
    units: list[Unit] | None = None,
    *,
    chapters: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Assemble full report.md; on failure leave the previous file untouched."""
    ensure_v2_directories(base)
    if units is None:
        units, errors = load_units_manifest(base, chapters=chapters)
        if errors:
            return "", errors
    unapproved = [
        unit.id for unit in units
        if not refresh_unit_currency(base, unit, project_root=base.parent)["report"]["current"]
    ]
    if unapproved:
        return "", ["报告单元未获得当前有效且有审阅者记录的批准：" + "、".join(unapproved)]
    return assemble_report(base, units, write=True)


def init_v2_project(base: Path, chapters: list[str], units: list[Unit]) -> None:
    ensure_v2_directories(base)
    from .units import write_units_manifest

    write_units_manifest(base, units)
