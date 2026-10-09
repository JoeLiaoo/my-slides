"""Recommend the next concrete workflow action from current project state."""

from __future__ import annotations

import argparse
import shlex

from ..browser_runtime import browser_status
from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..sources import scan_sources
from ..state import collect_units_status
from ..unit_workflow import validate_unit_report, validate_unit_spec
from ..units import assemble_report, load_units_manifest, unit_paths
from ..wiki import validate_wiki


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)

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
            return recommend(
                f"my-slides confirm report --unit {unit.id}",
                "报告已提交审批；必须由用户审阅文件后在自己的交互终端确认，Agent 不得执行此命令。",
                unit=unit.id, actor="human",
            )
        if row["report_current"] and (not row["report_approved_by"] or not row["report_approved_account"]):
            return recommend(f"my-slides approve report --unit {unit.id}", "旧审批记录没有审阅者信息；请重新提交供用户确认。", unit=unit.id)
        if not row["report_current"]:
            return recommend(f"my-slides approve report --unit {unit.id}", "报告内容有效，但当前版本尚未由用户确认；先提交审批申请。", unit=unit.id)

    assembled, assembly_errors = assemble_report(base, units, write=False)
    assembled_path = base / "reports" / "report.md"
    if assembly_errors:
        return recommend("my-slides assemble", "报告组装存在问题：" + "；".join(assembly_errors[:3]))
    if not assembled_path.is_file() or assembled_path.read_text(encoding="utf-8") != assembled:
        return recommend("my-slides assemble", "已批准报告单元，但整份报告尚未组装或已过期。")

    for unit in units:
        row = rows[unit.id]
        paths = unit_paths(base, unit.id)
        if not paths.spec.is_file():
            return recommend(f"my-slides prepare spec --unit {unit.id}", "Spec 文件尚未创建；先生成交接材料并撰写。", unit=unit.id)
        spec_errors = validate_unit_spec(base, unit)
        if spec_errors:
            return recommend(f"my-slides validate spec --unit {unit.id}", "Spec 需要修复：" + "；".join(spec_errors[:3]), unit=unit.id)
        if row["spec_pending"]:
            return recommend(
                f"my-slides confirm spec --unit {unit.id}",
                "Spec 已提交审批；必须由用户审阅文件后在自己的交互终端确认，Agent 不得执行此命令。",
                unit=unit.id, actor="human",
            )
        if row["spec_current"] and (not row["spec_approved_by"] or not row["spec_approved_account"]):
            return recommend(f"my-slides approve spec --unit {unit.id}", "旧审批记录没有审阅者信息；请重新提交供用户确认。", unit=unit.id)
        if not row["spec_current"]:
            return recommend(f"my-slides approve spec --unit {unit.id}", "Spec 尚未获得当前版本的用户确认；先提交审批申请。", unit=unit.id)

    for unit in units:
        row = rows[unit.id]
        if not unit_paths(base, unit.id).page.is_file():
            return recommend(f"my-slides prepare slides --unit {unit.id}", "单页 HTML 尚未创建；先生成交接材料并制作页面。", unit=unit.id)
        if not row["html_current"]:
            return recommend(f"my-slides slides build --unit {unit.id}", "此单元 HTML 尚未按当前 Spec 和主题构建。", unit=unit.id)

    if not (base / "slides" / "index.html").is_file():
        return recommend("my-slides slides build --all", "全部单页均已构建，但正式整套尚未生成。", unit="all")
    if any(not rows[unit.id]["check_current"] for unit in units):
        browser = browser_status()
        if not browser["playwright"]:
            return recommend("my-slides browser doctor", "尚未安装 Playwright；请按 README 的安装命令添加 [browser] 依赖，然后安装 Chromium。")
        if not browser["chromium_installed"]:
            return recommend("my-slides browser install", "所有页面已构建；安装 Chromium 后才能记录桌面和手机视口检查。")
        return recommend("my-slides slides check --all --browser", "正式整套尚未完成当前版本的浏览器检查。", unit="all")
    return recommend(None, "全部单元的报告、Spec、HTML 与浏览器检查均为当前版本。", actor="none")
