"""Recommend the next concrete workflow action from current project state."""

from __future__ import annotations

import argparse
import shlex

from ..approval_review import approval_mode
from ..browser_runtime import browser_status
from ..command_output import emit
from ..dependencies import fingerprint_json
from ..project import ensure_project, project_root, require_v2_project
from ..research import validate_number_list
from ..sources import scan_sources
from ..state import collect_units_status
from ..unit_workflow import validate_unit_report, validate_unit_spec
from ..units import assemble_report, load_units_manifest, unit_paths
from ..wiki import validate_wiki


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    if getattr(args, "all", False):
        return run_all(args, root, base, cfg)

    def recommend(command: str | None, reason: str, *, unit: str | None = None, actor: str = "agent") -> int:
        if command is not None and command.startswith("my-slides ") and not command.startswith("my-slides browser "):
            command += f" --project {shlex.quote(str(root))}"
        step = {"command": command, "unit": unit, "actor": actor, "reason": reason}
        human = "工作流已完成。" if command is None else f"下一步（{actor}）：{command}\n原因：{reason}"
        emit(args, {"project": str(root), "next": step}, human)
        return 0

    _, pending, removed = scan_sources(root, base, cfg)
    if pending or removed:
        return recommend(
            "my-slides prepare wiki",
            f"有 {len(pending)} 份新增或变化资料、{len(removed)} 份已移除资料。"
            "先整合 Wiki 并检查引用，再运行 sources mark-ingested；不要直接把未读资料标记为已整理。",
        )
    wiki_errors = validate_wiki(base, cfg)
    if wiki_errors:
        return recommend("my-slides validate wiki", "Wiki 尚有待修复的问题：" + "；".join(wiki_errors[:3]))

    units, errors = load_units_manifest(base, cfg.get("chapters", []))
    if errors:
        raise ValueError("；".join(errors))
    if not units:
        raise ValueError("units.json 中没有单元；请先补充单元清单")
    status = collect_units_status(base, chapters=cfg.get("chapters", []), project_root=root)
    chat_approval = approval_mode(cfg) == "chat"
    rows = {row["id"]: row for row in status["units"]}
    for unit in units:
        row = rows[unit.id]
        paths = unit_paths(base, unit.id)
        if not paths.report.is_file():
            return recommend(f"my-slides prepare report --unit {unit.id}", "报告文件尚未创建；先生成交接材料并撰写。", unit=unit.id)
        report_errors = validate_unit_report(base, unit)
        if report_errors:
            return recommend(f"my-slides validate report --unit {unit.id}", "报告需要修复：" + "；".join(report_errors[:3]), unit=unit.id)
        if row["report_pending"]:
            context = row.get("report_reconfirmation_context")
            if chat_approval:
                reason = (
                    f"报告内容未变，只需确认章节调整：{context}。把 review 的内容贴到对话中，等用户明确回复批准。"
                    if context else
                    "报告已提交审批。把 review 的内容贴到对话中，等用户明确回复批准。"
                )
                command = f"my-slides review report --unit {unit.id}"
            else:
                reason = (
                    f"报告内容未变，只需确认章节调整：{context}。必须由用户在自己的交互终端确认，Agent 不得执行此命令。"
                    if context else
                    "报告已提交审批；必须由用户审阅文件后在自己的交互终端确认，Agent 不得执行此命令。"
                )
                command = f"my-slides confirm report --unit {unit.id}"
            return recommend(command, reason, unit=unit.id, actor="human")
        if (
            row.get("report_latest_decision") == "rejected"
            and not row["report_current"]
            and not row["report_pending"]
        ):
            rejection = row.get("report_latest_rejection") or {}
            reason_text = (rejection.get("reason") or "").strip() or "（未提供原因）"
            return recommend(
                f"my-slides approve report --unit {unit.id}",
                f"用户驳回了报告：{reason_text}；Agent 请按驳回原因修改 reports/units/{unit.id}.md 后重新提交审批。",
                unit=unit.id,
            )
        if row["report_unattributed"]:
            return recommend(f"my-slides approve report --unit {unit.id}", "旧审批记录没有审阅者信息；请重新提交供用户确认。", unit=unit.id)
        if not row["report_current"]:
            return recommend(f"my-slides approve report --unit {unit.id}", "报告内容有效，但当前版本尚未由用户确认；先提交审批申请。", unit=unit.id)

    assembled, assembly_errors = assemble_report(base, units, write=False)
    assembled_path = base / "reports" / "report.md"
    if assembly_errors:
        return recommend("my-slides assemble", "报告组装存在问题：" + "；".join(assembly_errors[:3]))
    if not assembled_path.is_file() or assembled_path.read_text(encoding="utf-8") != assembled:
        return recommend("my-slides assemble", "已批准报告单元，但整份报告尚未组装或已过期。")

    research_errors = validate_number_list(base) if any(unit.role == "content" for unit in units) else []
    if research_errors:
        return recommend(
            "my-slides prepare evidence-research",
            "报告已组装；先整理可复核的公开数字并通过 evidence-research 校验，再撰写 Spec。",
        )

    for unit in units:
        row = rows[unit.id]
        paths = unit_paths(base, unit.id)
        if not paths.spec.is_file():
            return recommend(f"my-slides prepare spec --unit {unit.id}", "Spec 文件尚未创建；先生成交接材料并撰写。", unit=unit.id)
        spec_errors = validate_unit_spec(base, unit)
        if spec_errors:
            return recommend(f"my-slides validate spec --unit {unit.id}", "Spec 需要修复：" + "；".join(spec_errors[:3]), unit=unit.id)
        if row["spec_pending"]:
            if chat_approval:
                command = f"my-slides review spec --unit {unit.id}"
                reason = "Spec 已提交审批。把 review 的内容贴到对话中，等用户明确回复批准。"
            else:
                command = f"my-slides confirm spec --unit {unit.id}"
                reason = "Spec 已提交审批；必须由用户审阅文件后在自己的交互终端确认，Agent 不得执行此命令。"
            return recommend(command, reason, unit=unit.id, actor="human")
        if (
            row.get("spec_latest_decision") == "rejected"
            and not row["spec_current"]
            and not row["spec_pending"]
        ):
            rejection = row.get("spec_latest_rejection") or {}
            reason_text = (rejection.get("reason") or "").strip() or "（未提供原因）"
            return recommend(
                f"my-slides approve spec --unit {unit.id}",
                f"用户驳回了 Spec：{reason_text}；Agent 请按驳回原因修改 specs/units/{unit.id}.md 后重新提交审批。",
                unit=unit.id,
            )
        if row["spec_unattributed"]:
            return recommend(f"my-slides approve spec --unit {unit.id}", "旧审批记录没有审阅者信息；请重新提交供用户确认。", unit=unit.id)
        if not row["spec_current"]:
            return recommend(f"my-slides approve spec --unit {unit.id}", "Spec 尚未获得当前版本的用户确认；先提交审批申请。", unit=unit.id)

    for unit in units:
        if not unit_paths(base, unit.id).page.is_file():
            return recommend(f"my-slides prepare slides --unit {unit.id}", "小章节 HTML 尚未创建；先生成交接材料并按 Spec 页数制作页面。", unit=unit.id)

    deck_path = base / "slides" / "index.html"
    deck_state_path = base / ".state" / "slides.json"
    deck_state = {}
    if deck_state_path.is_file():
        try:
            import json

            deck_state = json.loads(deck_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            deck_state = {}
    expected_manifest = fingerprint_json([unit.to_dict() for unit in units])
    if deck_path.is_file() and deck_state.get("unit_manifest_sha256") != expected_manifest:
        return recommend("my-slides slides build --all", "单元顺序、章节或身份已变化，正式整套需要按当前清单重新生成。", unit="all")
    for unit in units:
        row = rows[unit.id]
        if not row["html_current"]:
            return recommend(f"my-slides slides build --unit {unit.id}", "此单元 HTML 尚未按当前 Spec 和主题构建。", unit=unit.id)
    if not deck_path.is_file():
        return recommend("my-slides slides build --all", "全部单页均已构建，但正式整套尚未生成。", unit="all")
    if getattr(args, "no_browser", False):
        from ..browser import check_units_on_deck
        structural = check_units_on_deck(base, deck_path, [unit.id for unit in units], browser=False)
        if structural["errors"]:
            return recommend("my-slides slides check --all", "结构检查需要修复：" + "；".join(structural["errors"][:3]), unit="all")
        return recommend(None, "结构检查通过；浏览器检查未做（本次规划选择不要求）。", actor="none")
    if any(not rows[unit.id]["check_current"] for unit in units):
        browser = browser_status()
        if not browser["playwright"]:
            return recommend("my-slides browser doctor", "尚未安装 Playwright；请按 README 的安装命令添加 [browser] 依赖，然后安装 Chromium。")
        if not browser["chromium_installed"]:
            return recommend("my-slides browser install", "所有页面已构建；安装 Chromium 后才能记录桌面和手机视口检查。")
        return recommend("my-slides slides check --all --browser", "正式整套尚未完成当前版本的浏览器检查。", unit="all")
    return recommend(None, "全部单元的报告、Spec、HTML 与浏览器检查均为当前版本。", actor="none")


def run_all(args: argparse.Namespace, root, base, cfg) -> int:
    """List outstanding work from the current files, grouped by who can act."""
    steps = []
    def add(command: str, reason: str, unit: str | None = None, actor: str = "agent"):
        if command.startswith("my-slides ") and not command.startswith("my-slides browser "):
            command += f" --project {shlex.quote(str(root))}"
        steps.append({"command": command, "unit": unit, "actor": actor, "reason": reason})

    _, pending, removed = scan_sources(root, base, cfg)
    if pending or removed:
        add("my-slides prepare wiki", f"有 {len(pending)} 份新增或变化资料、{len(removed)} 份已移除资料；先整理并复核 Wiki。")
    wiki_errors = validate_wiki(base, cfg)
    if wiki_errors:
        add("my-slides validate wiki", "Wiki 有待修复问题：" + "；".join(wiki_errors[:3]))
    units, errors = load_units_manifest(base, cfg.get("chapters", []))
    if errors: raise ValueError("；".join(errors))
    status = collect_units_status(base, chapters=cfg.get("chapters", []), project_root=root)
    rows = {row["id"]: row for row in status["units"]}
    chat_approval = approval_mode(cfg) == "chat"
    for unit in units:
        row = rows[unit.id]; paths = unit_paths(base, unit.id)
        if not paths.report.is_file(): add(f"my-slides prepare report --unit {unit.id}", "创建报告交接并撰写。", unit.id); continue
        report_errors = validate_unit_report(base, unit)
        if report_errors: add(f"my-slides validate report --unit {unit.id}", "修复报告：" + "；".join(report_errors[:3]), unit.id); continue
        if row["report_pending"]:
            add(f"my-slides {'review' if chat_approval else 'confirm'} report --unit {unit.id}", "报告正在等待用户审阅并批准。", unit.id, "human"); continue
        if row.get("report_latest_decision") == "rejected" and not row["report_current"]:
            add(f"my-slides approve report --unit {unit.id}", "按用户驳回意见修改报告后重新提交。", unit.id); continue
        if not row["report_current"]: add(f"my-slides approve report --unit {unit.id}", "提交当前报告供用户审批。", unit.id)
    assembled, assembly_errors = assemble_report(base, units, write=False)
    if assembly_errors: add("my-slides assemble", "修复报告组装问题：" + "；".join(assembly_errors[:3]))
    elif not (base / "reports/report.md").is_file() or (base / "reports/report.md").read_text(encoding="utf-8") != assembled:
        add("my-slides assemble", "组装当前已批准的报告单元。")
    if any(unit.role == "content" for unit in units) and validate_number_list(base): add("my-slides prepare evidence-research", "整理并核验可追溯的公开数字。")
    for unit in units:
        row = rows[unit.id]; paths = unit_paths(base, unit.id)
        if not paths.spec.is_file(): add(f"my-slides prepare spec --unit {unit.id}", "创建 Presentation Spec 交接并撰写。", unit.id); continue
        spec_errors = validate_unit_spec(base, unit)
        if spec_errors: add(f"my-slides validate spec --unit {unit.id}", "修复 Spec：" + "；".join(spec_errors[:3]), unit.id); continue
        if row["spec_pending"]:
            add(f"my-slides {'review' if chat_approval else 'confirm'} spec --unit {unit.id}", "Spec 正在等待用户审阅并批准。", unit.id, "human"); continue
        if row.get("spec_latest_decision") == "rejected" and not row["spec_current"]:
            add(f"my-slides approve spec --unit {unit.id}", "按用户驳回意见修改 Spec 后重新提交。", unit.id); continue
        if not row["spec_current"]: add(f"my-slides approve spec --unit {unit.id}", "提交当前 Spec 供用户审批。", unit.id)
    for unit in units:
        if not unit_paths(base, unit.id).page.is_file(): add(f"my-slides prepare slides --unit {unit.id}", "创建页面交接并按 Spec 制作 HTML。", unit.id)
    deck_path = base / "slides/index.html"; state_path = base / ".state/slides.json"; deck_state = {}
    if state_path.is_file():
        try:
            import json
            deck_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): pass
    if deck_path.is_file() and deck_state.get("unit_manifest_sha256") != fingerprint_json([unit.to_dict() for unit in units]):
        add("my-slides slides build --all", "按当前清单重新构建整套 Slides。", "all")
    else:
        for unit in units:
            if not rows[unit.id]["html_current"]: add(f"my-slides slides build --unit {unit.id}", "按当前 Spec 和主题重建页面。", unit.id)
        if not deck_path.is_file() and all(unit_paths(base, unit.id).page.is_file() for unit in units): add("my-slides slides build --all", "生成正式整套 Slides。", "all")
    if getattr(args, "no_browser", False) and deck_path.is_file() and all(rows[unit.id]["html_current"] for unit in units):
        from ..browser import check_units_on_deck
        structural = check_units_on_deck(base, deck_path, [unit.id for unit in units], browser=False)
        if structural["errors"]:
            add("my-slides slides check --all", "修复结构检查：" + "；".join(structural["errors"][:3]), "all")
    elif not getattr(args, "no_browser", False) and any(not rows[unit.id]["check_current"] for unit in units):
        browser = browser_status()
        command = "my-slides browser doctor" if not browser["playwright"] else "my-slides browser install" if not browser["chromium_installed"] else "my-slides slides check --all --browser"
        add(command, "完成当前版本的桌面与手机浏览器检查。", "all")
    grouped = {actor: [step for step in steps if step["actor"] == actor] for actor in ("agent", "human")}
    human = "工作流已完成。" if not steps else "全部待办：\n" + "\n".join(f"[{actor}] {step['command']} — {step['reason']}" for actor in ("agent", "human") for step in grouped[actor])
    emit(args, {"project": str(root), "steps": steps, "by_actor": grouped}, human)
    return 0
