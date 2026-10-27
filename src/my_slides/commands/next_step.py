"""Recommend the next concrete workflow action from current project state."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from ..approval_review import approval_mode
from ..command_output import emit
from ..delivery import last_delivery
from ..design_deck import deck_fingerprint, placeholder_pages, sync_deck
from ..design_workflow import check_status
from ..project import ensure_project, project_root, require_v2_project
from ..research import validate_number_list
from ..sources import scan_sources
from ..state import collect_units_status
from ..unit_workflow import validate_unit_report
from ..units import assemble_report, load_units_manifest, unit_paths
from ..wiki import validate_wiki


def _report_step(unit_id: str, row: dict[str, Any], base: Path, unit, chat_approval: bool) -> tuple[str, str, str] | None:
    """(command, reason, actor) for the first open report task of one unit."""
    if not unit_paths(base, unit_id).report.is_file():
        return f"my-slides prepare report --unit {unit_id}", "报告文件尚未创建；先生成交接材料并撰写。", "agent"
    report_errors = validate_unit_report(base, unit)
    if report_errors:
        return f"my-slides validate report --unit {unit_id}", "报告需要修复：" + "；".join(report_errors[:3]), "agent"
    if row["report_pending"]:
        context = row.get("report_reconfirmation_context")
        prefix = f"报告内容未变，只需确认章节调整：{context}。" if context else "报告已提交审批。"
        if chat_approval:
            return (f"my-slides review report --unit {unit_id}",
                    prefix + "把 review 的内容贴到对话中，等用户明确回复批准。", "human")
        return (f"my-slides confirm report --unit {unit_id}",
                prefix + "必须由用户审阅文件后在自己的交互终端确认，Agent 不得执行此命令。", "human")
    if row.get("report_latest_decision") == "rejected" and not row["report_current"]:
        rejection = row.get("report_latest_rejection") or {}
        reason_text = (rejection.get("reason") or "").strip() or "（未提供原因）"
        return (f"my-slides approve report --unit {unit_id}",
                f"用户驳回了报告：{reason_text}；Agent 请按驳回原因修改 reports/units/{unit_id}.md 后重新提交审批。", "agent")
    if row["report_unattributed"]:
        return f"my-slides approve report --unit {unit_id}", "旧审批记录没有审阅者信息；请重新提交供用户确认。", "agent"
    if not row["report_current"]:
        return f"my-slides approve report --unit {unit_id}", "报告内容有效，但当前版本尚未由用户确认；先提交审批申请。", "agent"
    return None


def collect_steps(root: Path, base: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Every outstanding step in workflow order; later stages wait for earlier ones."""
    steps: list[dict[str, Any]] = []

    def add(command: str, reason: str, unit: str | None = None, actor: str = "agent") -> None:
        if command.startswith("my-slides "):
            command += f" --project {shlex.quote(str(root))}"
        steps.append({"command": command, "unit": unit, "actor": actor, "reason": reason})

    _, pending, removed = scan_sources(root, base, cfg)
    if pending or removed:
        add("my-slides prepare wiki",
            f"有 {len(pending)} 份新增或变化资料、{len(removed)} 份已移除资料。"
            "先整合 Wiki 并检查引用，再运行 sources mark-ingested；不要直接把未读资料标记为已整理。")
    wiki_errors = validate_wiki(base, cfg)
    if wiki_errors:
        add("my-slides validate wiki", "Wiki 尚有待修复的问题：" + "；".join(wiki_errors[:3]))

    units, errors = load_units_manifest(base, cfg.get("chapters", []))
    if errors:
        raise ValueError("；".join(errors))
    if not units:
        raise ValueError("units.json 中没有单元；请先补充单元清单")
    status = collect_units_status(base, chapters=cfg.get("chapters", []), project_root=root)
    rows = {row["id"]: row for row in status["units"]}
    chat_approval = approval_mode(cfg) == "chat"
    for unit in units:
        step = _report_step(unit.id, rows[unit.id], base, unit, chat_approval)
        if step:
            add(step[0], step[1], unit.id, step[2])
    if not all(rows[unit.id]["report_current"] for unit in units):
        return steps

    assembled, assembly_errors = assemble_report(base, units, write=False)
    assembled_path = base / "reports" / "report.md"
    if assembly_errors:
        add("my-slides assemble", "报告组装存在问题：" + "；".join(assembly_errors[:3]))
    elif not assembled_path.is_file() or assembled_path.read_text(encoding="utf-8") != assembled:
        add("my-slides assemble", "已批准报告单元，但整份报告尚未组装或已过期。")
    if any(unit.role == "content" for unit in units) and validate_number_list(base):
        add("my-slides prepare evidence-research", "报告已批准；先整理可复核的公开数字并通过 evidence-research 校验，再写页面。")
    if steps:
        return steps

    for unit in units:
        if not rows[unit.id]["pages"]:
            add(f"my-slides prepare slides --unit {unit.id}",
                "该单元还没有 Design 页面；生成写页交接后按交接写页，再运行 slides build。", unit.id)
        elif placeholder_pages(base, unit.id):
            add(f"my-slides prepare slides --unit {unit.id}",
                "页面仍是占位内容（含“[待写：”）；按交接依据已批准报告写页。", unit.id)
    if steps:
        return steps
    if sync_deck(base, cfg, [], write=False)["deck_changed"]:
        add("my-slides slides build --all", "deck.json 的页序或分节与 units.json 不一致，需要同步。", "all")
        return steps
    if not check_status(base)["current"]:
        add("my-slides slides check --all", "Design deck 尚未通过当前版本的结构检查。", "all")
        return steps
    delivered = last_delivery(base)
    if not delivered or delivered.get("deck_fingerprint") != deck_fingerprint(base):
        add("my-slides slides open",
            "结构检查已通过。请用户在 5173 审阅整套 Slides：小改直接手调，大改口述给 Agent；"
            "用户确认满意后运行 my-slides export 导出交付（导出需要宿主在运行）。", "all", "human")
    return steps


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    steps = collect_steps(root, base, cfg)
    if getattr(args, "all", False):
        grouped = {actor: [step for step in steps if step["actor"] == actor] for actor in ("agent", "human")}
        human = "工作流已完成。" if not steps else "全部待办：\n" + "\n".join(
            f"[{actor}] {step['command']} — {step['reason']}" for actor in ("agent", "human") for step in grouped[actor]
        )
        emit(args, {"project": str(root), "steps": steps, "by_actor": grouped}, human)
        return 0
    if steps:
        step = steps[0]
        human = f"下一步（{step['actor']}）：{step['command']}\n原因：{step['reason']}"
    else:
        step = {"command": None, "unit": None, "actor": "none",
                "reason": "全部单元的报告已批准，Design deck 已通过检查并已导出交付当前版本。"}
        human = "工作流已完成。"
    emit(args, {"project": str(root), "next": step}, human)
    return 0
