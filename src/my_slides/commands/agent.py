"""Install the project workflow skill."""

from __future__ import annotations

import argparse

from ..agent_workflow import install_agent_workflow
from ..command_output import emit
from ..project import project_root


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project, discover=False)
    result = install_agent_workflow(root)
    emit(
        args, result,
        "已安装：" + (", ".join(result["installed"]) or "无")
        + ("；已保留现有文件：" + ", ".join(result["preserved"]) if result["preserved"] else ""),
    )
    return 0
