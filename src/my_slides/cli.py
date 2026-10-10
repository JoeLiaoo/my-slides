"""Argument parsing and dispatch for the my-slides v2 CLI."""

from __future__ import annotations

import argparse
import json
import sys

from . import format_version
from .commands import agent, approve, assemble, browser, confirm, doctor, help, next_step, renderer, slides, sources, status, units, validate
from .commands.init import init_project
from .commands.prepare import prepare


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
        description="投资项目 Wiki、报告与 HTML Slides 本地工作流",
        epilog="首次使用请运行 my-slides help；具体参数请运行 my-slides <命令> --help。",
    )
    parser.add_argument("-V", "--version", action=_PrintVersion)
    sub = parser.add_subparsers(dest="command", required=True)
    guide = sub.add_parser("help", help="查看面向首次使用的 Agent 工作流指南（无需项目目录）")
    guide.add_argument("--json", action="store_true", help="以 JSON 输出指南")
    init = sub.add_parser("init", help="初始化 v2 单元格式投资项目工作区")
    init.add_argument("--project", help="项目目录，默认当前目录")
    init.add_argument("--source-dir", action="append", help="资料目录（相对项目目录，可重复指定）")
    init.add_argument("--force", action="store_true", help="补全基础文件并重写项目配置")
    init.add_argument("--json", action="store_true")
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
    prep.add_argument("kind", choices=("wiki", "report", "spec", "slides"))
    prep.add_argument("--project")
    prep.add_argument("--json", action="store_true")
    prep.add_argument("--question", help="针对项目 Wiki 提出问题；省略时准备资料整理任务")
    add_unit_selectors(prep)
    validate = sub.add_parser("validate", help="检查 Wiki、报告或 Spec")
    validate.add_argument("kind", choices=("wiki", "report", "spec"))
    validate.add_argument("--project")
    validate.add_argument("--json", action="store_true")
    add_unit_selectors(validate)
    approve = sub.add_parser("approve", help="提交报告或 Spec 单元供用户审批，不会直接批准")
    approve.add_argument("kind", choices=("report", "spec"))
    approve.add_argument("--project")
    approve.add_argument("--json", action="store_true")
    add_unit_selectors(approve)
    confirm = sub.add_parser("confirm", help="用户在交互终端确认一个待审批单元")
    confirm.add_argument("kind", choices=("report", "spec"))
    confirm.add_argument("--unit", required=True, metavar="ID", help="要确认的单元 ID；每次只能确认一个")
    confirm.add_argument("--project")
    assemble = sub.add_parser("assemble", help="v2：将报告单元组装为 reports/report.md")
    assemble.add_argument("--project")
    assemble.add_argument("--json", action="store_true")
    renderer = sub.add_parser("renderer", help="检查或安装 ECharts 与 Lucide 本地渲染器")
    renderer_sub = renderer.add_subparsers(dest="renderer_command", required=True)
    for name, help_text in (("doctor", "检查 Node.js、npm 与锁定的渲染器版本"), ("install", "安装锁定版本的本地渲染依赖")):
        command = renderer_sub.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")
    browser = sub.add_parser("browser", help="检查或安装离线 Slides 浏览器验证环境")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    for name, help_text in (("doctor", "检查 Playwright 与 Chromium"), ("install", "安装 Playwright Chromium")):
        command = browser_sub.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")
    agent = sub.add_parser("agent", help="安装或检查 agent 工作流指引")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_install = agent_sub.add_parser("install", help="安装项目级工作流技能，不覆盖现有文件")
    agent_install.add_argument("--project", help="项目目录，默认当前目录")
    agent_install.add_argument("--json", action="store_true")
    slides = sub.add_parser("slides", help="合并并检查 HTML Slides")
    slides_sub = slides.add_subparsers(dest="slides_command", required=True)
    for name, help_text in (("build", "合并所选单元的 HTML 页面"), ("check", "检查所选单元和合并文件")):
        command = slides_sub.add_parser(name, help=help_text)
        command.add_argument("--project")
        command.add_argument("--json", action="store_true")
        command.add_argument("--browser", action="store_true", help="用桌面与手机视口运行 Chromium 验证")
        add_unit_selectors(command)
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
    next_command.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    handlers = {
        "help": help.run,
        "init": init_project,
        "sources": sources.run,
        "prepare": prepare,
        "validate": validate.run,
        "approve": approve.run,
        "confirm": confirm.run,
        "assemble": assemble.run,
        "slides": slides.run,
        "units": units.run,
        "doctor": doctor.run,
        "status": status.run,
        "next": next_step.run,
        "renderer": renderer.run,
        "browser": browser.run,
        "agent": agent.run,
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
