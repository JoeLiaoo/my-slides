"""Argument parsing and dispatch for the thin my-slides CLI."""

from __future__ import annotations

import argparse
import json
import sys

from . import format_version, thin
from .commands import help


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
        description="研究正文到 beautiful 长文和 Design+Slides 的薄壳工作区",
        epilog="首次使用请运行 my-slides help；具体参数请运行 my-slides <命令> --help。",
    )
    parser.add_argument("-V", "--version", action=_PrintVersion)
    sub = parser.add_subparsers(dest="command", required=True)
    guide = sub.add_parser("help", help="查看 Agent 薄壳工作流指南（无需项目目录）")
    guide.add_argument("--json", action="store_true", help="以 JSON 输出指南")
    init = sub.add_parser("init", help="只创建 my-slides/project.json")
    init.add_argument("--project", help="项目目录，默认当前目录")
    init.add_argument("--json", action="store_true")
    present = sub.add_parser("present", help="逐目标校验或输出 Agent 呈现交接；未完成时退出非零")
    present.add_argument("--project", help="项目目录，默认当前目录")
    present.add_argument("--target", choices=("beautiful", "slides"), help="仅处理指定目标")
    present.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    handlers = {"help": help.run, "init": thin.init, "present": thin.present}
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
