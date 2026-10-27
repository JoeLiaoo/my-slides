"""Argument parsing and dispatch for the my-slides v2 CLI."""

from __future__ import annotations

import argparse
import json
import sys

from . import format_version
from .commands import agent, approve, assemble, chapters, clean, confirm, doctor, export, help, next_step, reject, review, revoke, slides, sources, status, units, validate, withdraw
from .commands.prepare import prepare
from .state import APPROVAL_KINDS
from . import thin


class _PrintVersion(argparse.Action):
    """Read Git metadata only when the user asks for the version."""

    def __init__(self, option_strings: list[str], dest: str, nargs: int | str | None = 0, **kwargs: object) -> None:
        super().__init__(option_strings, dest, nargs=nargs, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        print(format_version(parser.prog))
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="my-slides",
        description="投资项目 Wiki、报告与 Design+Slides 本地工作流",
        epilog="首次使用请运行 my-slides help；具体参数请运行 my-slides <命令> --help。",
    )
    parser.add_argument("-V", "--version", action=_PrintVersion)
    sub = parser.add_subparsers(dest="command", required=True)
    guide = sub.add_parser("help", help="查看面向首次使用的 Agent 工作流指南（无需项目目录）")
    guide.add_argument("--json", action="store_true", help="以 JSON 输出指南")
    init = sub.add_parser("init", help="创建薄壳 project.json 工作区")
    init.add_argument("--project", help="项目目录，默认当前目录")
    init.add_argument("--source-dir", action="append", help="资料目录（相对项目目录，可重复指定）")
    init.add_argument("--force", action="store_true", help="补全基础文件并重写项目配置")
    init.add_argument("--legacy", action="store_true", help="显式创建旧 v2 单元工作区（仅供旧流程）")
    init.add_argument("--json", action="store_true")
    present = sub.add_parser("present", help="逐目标校验或输出 Agent 呈现交接；未完成时退出非零")
    present.add_argument("--project", help="项目目录，默认当前目录")
    present.add_argument("--target", choices=("beautiful", "slides"), help="仅处理指定目标")
    present.add_argument("--json", action="store_true")
    sources = sub.add_parser("sources", help="扫描或确认资料")
    source_sub = sources.add_subparsers(dest="sources_command", required=True)
    for name, help_text in (("scan", "扫描 Markdown 变化"), ("mark-ingested", "确认 agent 已整理当前变更资料")):
        command = source_sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        if name == "mark-ingested":
            command.add_argument("paths", nargs="*", help="项目相对路径；省略时确认所有待整理资料")
    def add_unit_selectors(command: argparse.ArgumentParser) -> None:
        command.add_argument("--unit", action="append", dest="units", metavar="ID", help="v2 单元 ID（可重复）")
        command.add_argument("--changed", action="store_true", help="v2：仅处理状态显示受影响/阻塞的单元")
        command.add_argument("--all", dest="all_units", action="store_true", help="v2：处理全部单元")

    prep = sub.add_parser("prepare", help="生成 agent 阶段交接材料")
    prep.add_argument("kind", choices=("wiki", "report", "evidence-research", "slides"))
    prep.add_argument("--project")
    prep.add_argument("--json", action="store_true")
    prep.add_argument("--question", help="针对项目 Wiki 提出问题；省略时准备资料整理任务")
    add_unit_selectors(prep)
    validate = sub.add_parser("validate", help="检查 Wiki、报告或证据数字清单")
    validate.add_argument("kind", choices=("wiki", "report", "evidence-research"))
    validate.add_argument("--project")
    validate.add_argument("--json", action="store_true")
    add_unit_selectors(validate)
    approve = sub.add_parser("approve", help="提交报告单元供用户审批，不会直接批准")
    approve.add_argument("kind", choices=APPROVAL_KINDS)
    approve.add_argument("--project")
    approve.add_argument("--chapter", help="一次提交该大章节下的全部小章节")
    approve.add_argument("--json", action="store_true")
    add_unit_selectors(approve)
    review = sub.add_parser("review", help="展示待审批内容、差异和确认短语，供对话审阅")
    review.add_argument("kind", choices=APPROVAL_KINDS)
    review.add_argument("--unit", metavar="ID")
    review.add_argument("--chapter")
    review.add_argument("--project")
    review.add_argument("--json", action="store_true")
    confirm = sub.add_parser("confirm", help="确认一个待审批小章节，或在对话中确认一整章")
    confirm.add_argument("kind", choices=APPROVAL_KINDS)
    confirm.add_argument("--unit", metavar="ID", help="要确认的小章节；与 --chapter 二选一")
    confirm.add_argument("--chapter", help="确认该大章节下全部已提交的小章节；必须配合 --via chat")
    confirm.add_argument("--via", choices=("chat",), help="对话确认。需要 --phrase 和 --user-reply")
    confirm.add_argument("--phrase", help="review 给出的 APPROVE 短语")
    confirm.add_argument("--user-reply", dest="user_reply", help="用户在对话中的原话")
    confirm.add_argument("--reviewer", help="审批人；省略时使用 project.yaml 的 reviewer")
    confirm.add_argument("--project")
    reject = sub.add_parser("reject", help="驳回一个待审批小章节，或在对话中驳回一整章")
    reject.add_argument("kind", choices=APPROVAL_KINDS)
    reject.add_argument("--unit", metavar="ID", help="要驳回的小章节；与 --chapter 二选一")
    reject.add_argument("--chapter", help="驳回该大章节下全部已提交的小章节；必须配合 --via chat")
    reject.add_argument("--reason", required=True, help="驳回原因")
    reject.add_argument("--via", choices=("chat",), help="对话驳回。需要 --phrase 和 --user-reply")
    reject.add_argument("--phrase", help="review 给出的 REJECT 短语")
    reject.add_argument("--user-reply", dest="user_reply", help="用户在对话中的原话")
    reject.add_argument("--reviewer", help="审批人；省略时使用 project.yaml 的 reviewer")
    reject.add_argument("--json", action="store_true")
    reject.add_argument("--project")
    withdraw = sub.add_parser("withdraw", help="Agent 撤回自己提交的待审批申请")
    withdraw.add_argument("kind", choices=APPROVAL_KINDS)
    withdraw.add_argument("--unit", metavar="ID", required=True, help="要撤回的小章节")
    withdraw.add_argument("--project")
    withdraw.add_argument("--json", action="store_true")
    revoke = sub.add_parser("revoke", help="用户撤回一个已有的报告批准")
    revoke.add_argument("kind", choices=APPROVAL_KINDS)
    revoke.add_argument("--unit", metavar="ID", help="要撤回批准的小章节；与 --chapter 二选一")
    revoke.add_argument("--chapter", help="撤回该大章节下全部已批准的报告；必须配合 --via chat")
    revoke.add_argument("--reason", help="撤回原因；建议在 chat 模式下提供原文")
    revoke.add_argument("--via", choices=("chat",), help="对话撤回。第一次执行会展示已批准版本与 REVOKE 短语；用户同意后带 --phrase 和 --user-reply 再执行一次")
    revoke.add_argument("--phrase", help="revoke 上一步返回的 REVOKE 短语")
    revoke.add_argument("--user-reply", dest="user_reply", help="用户在对话中的原话")
    revoke.add_argument("--reviewer", help="审批人；省略时使用 project.yaml 的 reviewer")
    revoke.add_argument("--json", action="store_true")
    revoke.add_argument("--project")
    assemble = sub.add_parser("assemble", help="v2：将报告单元组装为 reports/report.md")
    assemble.add_argument("--project")
    assemble.add_argument("--json", action="store_true")
    agent = sub.add_parser("agent", help="安装或检查 agent 工作流指引")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_install = agent_sub.add_parser("install", help="安装项目级工作流技能，不覆盖现有文件")
    agent_install.add_argument("--project", help="项目目录，默认当前目录")
    agent_install.add_argument("--json", action="store_true")
    agent_doctor = agent_sub.add_parser("doctor", help="检查已安装工作流指引是否缺失或与当前版本不同")
    agent_doctor.add_argument("--project", help="项目目录，默认当前目录")
    agent_doctor.add_argument("--json", action="store_true")
    slides = sub.add_parser("slides", help="同步、检查并打开 Design+Slides 页面")
    slides_sub = slides.add_subparsers(dest="slides_command", required=True)
    slides_build = slides_sub.add_parser("build", help="按 units.json 同步 Design deck 页序与分节，给缺页单元补占位页")
    slides_check = slides_sub.add_parser("check", help="运行 Design 结构检查，并核对每个单元都有页面")
    slides_check.add_argument("--browser", action="store_true", help="同时运行 Design 渲染检查（需要宿主在运行）")
    slides_check.add_argument("--strict", action="store_true", help="Design 检查的警告也算失败")
    for command in (slides_build, slides_check):
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        add_unit_selectors(command)
    slides_open = slides_sub.add_parser("open", help="给出 5173 审阅链接和启动宿主的命令")
    slides_open.add_argument("--project")
    slides_open.add_argument("--json", action="store_true")
    units = sub.add_parser("units", help="管理 v2 内容单元清单")
    units_sub = units.add_subparsers(dest="units_command", required=True)
    units_list = units_sub.add_parser("list", help="列出单元身份、章节与产物是否齐全")
    units_list.add_argument("--project")
    units_list.add_argument("--json", action="store_true")
    units_add = units_sub.add_parser("add", help="新增内容单元")
    units_add.add_argument("id")
    units_add.add_argument("--chapter", required=True)
    units_add.add_argument("--title", help="小章节显示名，例如「需求分析」；省略时只记录单元 ID")
    units_add.add_argument("--after")
    units_add.add_argument("--role", choices=("content",), default="content")
    units_add.add_argument("--project")
    units_add.add_argument("--json", action="store_true")
    units_remove = units_sub.add_parser("remove", help="预览删除影响；添加 --yes 移入可恢复回收区")
    units_remove.add_argument("id")
    units_remove.add_argument("--yes", action="store_true")
    units_remove.add_argument("--project")
    units_remove.add_argument("--json", action="store_true")
    units_move = units_sub.add_parser("move", help="调整单元顺序或章节")
    units_move.add_argument("id")
    placement = units_move.add_mutually_exclusive_group()
    placement.add_argument("--after", metavar="ID", help="放到该单元之后；目标单元必须属于目标章节")
    placement.add_argument("--before", metavar="ID", help="放到该单元之前；用于移到章节首位")
    units_move.add_argument("--chapter", help="目标章节；省略 --after 和 --before 时放到该章末尾，空章节因此可以接收单元")
    units_move.add_argument("--project")
    units_move.add_argument("--json", action="store_true")
    units_rename = units_sub.add_parser("rename", help="重命名单元并迁移其产物")
    units_rename.add_argument("old_id")
    units_rename.add_argument("new_id")
    units_rename.add_argument("--project")
    units_rename.add_argument("--json", action="store_true")
    units_retitle = units_sub.add_parser("retitle", help="只修改小章节显示名，不改动已批准内容")
    units_retitle.add_argument("id")
    units_retitle.add_argument("title")
    units_retitle.add_argument("--project")
    units_retitle.add_argument("--json", action="store_true")
    units_restore = units_sub.add_parser("restore", help="从可恢复回收区恢复单元")
    units_restore.add_argument("trash_id")
    units_restore.add_argument("--project")
    units_restore.add_argument("--json", action="store_true")
    trash = units_sub.add_parser("trash", help="列出回收区中的单元")
    trash_sub = trash.add_subparsers(dest="trash_command", required=True)
    trash_list = trash_sub.add_parser("list", help="列出可恢复的删除记录")
    trash_list.add_argument("--project")
    trash_list.add_argument("--json", action="store_true")
    chapters = sub.add_parser("chapters", help="管理项目报告大章节（同步 project.yaml、units.json 与 wiki/index.md）")
    chapters_sub = chapters.add_subparsers(dest="chapters_command", required=True)
    chapters_list = chapters_sub.add_parser("list", help="列出大章节与所含小章节")
    chapters_list.add_argument("--project")
    chapters_list.add_argument("--json", action="store_true")
    chapters_add = chapters_sub.add_parser("add", help="新增大章节")
    chapters_add.add_argument("name")
    chapters_add.add_argument("--after", help="插入到该章节之后")
    chapters_add.add_argument("--project")
    chapters_add.add_argument("--json", action="store_true")
    chapters_rename = chapters_sub.add_parser("rename", help="重命名大章节并同步三处存储")
    chapters_rename.add_argument("old")
    chapters_rename.add_argument("new")
    chapters_rename.add_argument("--project")
    chapters_rename.add_argument("--json", action="store_true")
    chapters_remove = chapters_sub.add_parser("remove", help="删除大章节（仍有小章节时拒绝）")
    chapters_remove.add_argument("name")
    chapters_remove.add_argument("--project")
    chapters_remove.add_argument("--json", action="store_true")
    chapters_move = chapters_sub.add_parser("move", help="调整大章节顺序")
    chapters_move.add_argument("name")
    placement = chapters_move.add_mutually_exclusive_group()
    placement.add_argument("--after", metavar="CHAPTER", help="放到该章节之后")
    placement.add_argument("--before", metavar="CHAPTER", help="放到该章节之前")
    chapters_move.add_argument("--project")
    chapters_move.add_argument("--json", action="store_true")
    export_cmd = sub.add_parser("export", help="通过运行中的 Design 宿主导出离线 HTML，并在 .state/deliveries.json 记录")
    export_cmd.add_argument("--project")
    export_cmd.add_argument("--output", help="导出目录；省略时写到项目根")
    export_cmd.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor", help="检查项目工作区基础结构")
    doctor.add_argument("--project")
    doctor.add_argument("--json", action="store_true")
    status = sub.add_parser("status", help="查看项目阶段、待整理资料与单元状态")
    status.add_argument("--project")
    status.add_argument("--json", action="store_true")
    status.add_argument(
        "--unit",
        action="append",
        dest="units",
        metavar="ID",
        help="v2：查看指定单元状态（可重复）；省略则列出全部单元骨架",
    )
    next_command = sub.add_parser("next", help="查看下一步操作、目标单元和原因")
    next_command.add_argument("--project")
    next_command.add_argument("--all", action="store_true", help="列出当前全部待办，并按 Agent / 用户分组")
    next_command.add_argument("--json", action="store_true")
    clean = sub.add_parser("clean", help="预览或清理过期 work 交接文件与 Wiki 快照")
    clean.add_argument("--project")
    clean.add_argument("--older-than-days", type=int, default=30, help="仅清理超过指定天数的内容，默认 30 天")
    clean.add_argument("--yes", action="store_true", help="实际删除预览列出的内容；默认仅预览")
    clean.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    handlers = {
        "help": help.run,
        "init": thin.init,
        "present": thin.present,
        "sources": sources.run,
        "prepare": prepare,
        "validate": validate.run,
        "approve": approve.run,
        "review": review.run,
        "confirm": confirm.run,
        "reject": reject.run,
        "withdraw": withdraw.run,
        "revoke": revoke.run,
        "assemble": assemble.run,
        "slides": slides.run,
        "units": units.run,
        "chapters": chapters.run,
        "export": export.run,
        "doctor": doctor.run,
        "status": status.run,
        "next": next_step.run,
        "agent": agent.run,
        "clean": clean.run,
    }
    try:
        code = handlers[args.command](args)
    except (OSError, ValueError, RuntimeError) as exc:
        message = str(exc)
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"错误：{message}", file=sys.stderr)
        code = 2
    except Exception as exc:  # noqa: BLE001 — CLI must never dump a traceback to users
        message = f"未预期错误：{exc}"
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"错误：{message}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
