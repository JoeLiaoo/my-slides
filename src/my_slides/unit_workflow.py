"""Per-unit prepare, validation, and approval for v2 projects."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .dependencies import fingerprint_file
from .state import (
    collect_units_status,
    mark_report_approved,
    read_unit_state,
    refresh_unit_currency,
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
) -> list[Unit]:
    flags = sum(bool(x) for x in (unit_ids, changed, all_units))
    if flags > 1:
        raise ValueError("--unit、--changed、--all 只能三选一")
    units, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        raise UnitsError("；".join(errors))
    if not units:
        raise UnitsError("units.json 中没有单元")
    by_id = {unit.id: unit for unit in units}
    if all_units or (not unit_ids and not changed):
        if not all_units and not unit_ids and not changed:
            raise ValueError("v2 项目请指定 --unit <id>、--changed 或 --all")
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


def validate_unit_spec(base: Path, unit: Unit) -> list[str]:
    path = unit_paths(base, unit.id).spec
    errors: list[str] = []
    if not path.is_file():
        return [f"缺少 Spec 单元：specs/units/{unit.id}.md"]
    text = path.read_text(encoding="utf-8").strip()
    matches = list(re.finditer(r"^##\s+Slide\s+(\d+)\s+[—-].*$", text, flags=re.MULTILINE))
    if not matches:
        errors.append(f"{unit.id}：未找到分页标题（格式：## Slide 1 — 标题）")
        return errors
    if len(matches) != 1:
        errors.append(f"{unit.id}：每个 Spec 单元只能定义一页（找到 {len(matches)} 个 Slide 标题）")
    required = ("目的", "核心结论", "展示内容", "证据与来源", "限定条件", "报告段落映射", "布局意图", "图标需求")
    page = text[matches[0].start():]
    page_id = re.search(r"^页面 ID\s*[：:]\s*(\S+)\s*$", page, flags=re.MULTILINE)
    if not page_id:
        errors.append(f"{unit.id}：缺少页面 ID")
    elif page_id.group(1) != unit.id:
        errors.append(f"{unit.id}：页面 ID 必须与单元 ID 一致（当前为 {page_id.group(1)}）")
    role = re.search(r"^页面角色\s*[：:]\s*(cover|content)\s*$", page, flags=re.MULTILINE | re.IGNORECASE)
    if not role:
        errors.append(f"{unit.id}：页面角色必须填写 cover 或 content")
    elif role.group(1).lower() != unit.role:
        errors.append(f"{unit.id}：页面角色 {role.group(1)} 与 units.json 中的 {unit.role} 不一致")
    for heading in required:
        if not re.search(rf"^###\s+{re.escape(heading)}\s*$", page, flags=re.MULTILINE):
            errors.append(f"{unit.id}：缺少 ### {heading}")
    mapping = re.search(r"^###\s+报告段落映射\s*\n(.*?)(?=^###\s|\Z)", page, flags=re.MULTILINE | re.DOTALL)
    if mapping and not mapping.group(1).strip():
        errors.append(f"{unit.id}：报告段落映射不能为空")
    errors.extend(f"{unit.id}：{msg}" for msg in validate_local_markdown_links(text, path))
    return errors


def prepare_unit_handoff(
    base: Path,
    root: Path,
    units: list[Unit],
    kind: str,
) -> list[Path]:
    ensure_v2_directories(base)
    out_dir = base / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    if kind == "slides":
        from importlib.resources import files

        examples = files("my_slides").joinpath("slides_theme").joinpath("component-examples.md").read_text(encoding="utf-8")
        component_examples = examples.strip()
    else:
        component_examples = ""
    for unit in units:
        output = out_dir / kind / f"{unit.id}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# {kind} 单元交接：{unit.id}",
            "",
            f"项目目录：{root}",
            f"工作区：{base}",
            "规则：只改本单元对应的 reports/units、specs/units 或 slides/pages 文件；",
            "不要编辑组装产物 reports/report.md（由 CLI 组装）。",
            "",
        ]
        if component_examples:
            lines.extend([component_examples, ""])
        paths = unit_paths(base, unit.id)
        lines.extend(
            [
                f"## {unit.id}",
                f"- 章节：{unit.chapter}",
                f"- 角色：{unit.role}",
                f"- 报告：{paths.report.relative_to(base).as_posix()}",
                f"- Spec：{paths.spec.relative_to(base).as_posix()}",
                f"- HTML：{paths.page.relative_to(base).as_posix()}",
                "",
            ]
        )
        if kind == "report":
            lines.append("请撰写完整论证、证据与限定条件，并用普通 Markdown 链接引用 Wiki/资料。")
        elif kind == "spec":
            lines.append("请写恰好一页 Spec，页面 ID 必须等于单元 ID；图表数据放在 echarts-spec 代码块。")
        else:
            lines.append("请生成单页 HTML 片段，根元素设置 data-unit-id 与 data-page-role。")
        lines.append("")
        output.write_text("\n".join(lines), encoding="utf-8")
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
) -> dict[str, Any]:
    errors = validate_unit_report(base, unit)
    if errors:
        raise UnitsError("；".join(errors))
    state = mark_report_approved(
        base, unit, project_root=project_root or base.parent, when=when,
        approved_by=approved_by, approved_account=approved_account,
    )
    # Keep assembled report in sync after successful unit approve batches (caller may assemble).
    return state


def approve_unit_spec(
    base: Path,
    unit: Unit,
    *,
    when: str,
    project_root: Path | None = None,
    approved_by: str | None = None,
    approved_account: str | None = None,
) -> dict[str, Any]:
    errors = validate_unit_spec(base, unit)
    if errors:
        raise UnitsError("；".join(errors))
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    if not state["report"]["current"]:
        raise UnitsError(f"{unit.id}：报告尚未批准或已失效，请先 approve report --unit {unit.id}")
    paths = unit_paths(base, unit.id)
    spec_sha = fingerprint_file(paths.spec)
    report_sha = state["report"]["approved_sha256"]
    report_input = state["report"]["approved_input_fingerprint"]
    state["spec"] = {
        "content_sha256": spec_sha,
        "report_sha256": report_sha,
        "report_input_fingerprint": report_input,
        "approved_sha256": spec_sha,
        "approved_at": when,
        "approved_by": approved_by,
        "approved_account": approved_account,
        "pending_approval": None,
        "pending_current": False,
        "current": True,
    }
    # HTML must be rebuilt against the new Spec — never auto-revive.
    if state["html"].get("build_sha256"):
        state["html"]["current"] = False
        state["check"]["current"] = False
        state["reasons"] = ["Spec 已重新批准，HTML 需按新 Spec 更新"]
    else:
        state["reasons"] = []
    write_unit_state(base, unit.id, state)
    return state


def request_unit_approval(
    base: Path,
    unit: Unit,
    kind: str,
    *,
    when: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Record exactly which report or Spec version awaits human review."""
    if kind not in {"report", "spec"}:
        raise ValueError(f"未知审批类型：{kind}")
    errors = validate_unit_report(base, unit) if kind == "report" else validate_unit_spec(base, unit)
    if errors:
        raise UnitsError("；".join(errors))
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    if kind == "spec" and not state["report"]["current"]:
        raise UnitsError(f"{unit.id}：报告尚未批准或已失效，请先完成报告审批")
    request = {
        "requested_at": when,
        "content_sha256": state[kind]["content_sha256"],
    }
    if kind == "report":
        request["input_fingerprint"] = state["report"]["input_fingerprint"]
    else:
        request["report_sha256"] = state["report"]["approved_sha256"]
        request["report_input_fingerprint"] = state["report"]["approved_input_fingerprint"]
    state[kind]["pending_approval"] = request
    state[kind]["pending_current"] = True
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
) -> dict[str, Any]:
    """Apply a current review request after the CLI's interactive confirmation."""
    if kind not in {"report", "spec"}:
        raise ValueError(f"未知审批类型：{kind}")
    if not approved_by.strip() or not approved_account.strip():
        raise ValueError("审批人和本机账户不能为空")
    state = refresh_unit_currency(base, unit, project_root=project_root or base.parent)
    if not state[kind]["pending_current"]:
        raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请，或申请后内容/依赖已变化；请重新运行 approve {kind} --unit {unit.id}")
    if kind == "report":
        return approve_unit_report(
            base, unit, when=when, project_root=project_root,
            approved_by=approved_by.strip(), approved_account=approved_account.strip(),
        )
    return approve_unit_spec(
        base, unit, when=when, project_root=project_root,
        approved_by=approved_by.strip(), approved_account=approved_account.strip(),
    )


def assemble_after_report_approvals(base: Path, units: list[Unit] | None = None) -> tuple[str, list[str]]:
    """Assemble full report.md; on failure leave the previous file untouched."""
    ensure_v2_directories(base)
    return assemble_report(base, units, write=True)


def init_v2_project(base: Path, chapters: list[str], units: list[Unit]) -> None:
    ensure_v2_directories(base)
    from .units import write_units_manifest

    write_units_manifest(base, units)
