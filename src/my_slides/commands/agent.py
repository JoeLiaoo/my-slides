"""Install the project workflow skill."""

from __future__ import annotations

import argparse

from ..agent_workflow import check_agent_workflow, install_agent_workflow
from ..command_output import emit
from ..project import project_root


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project, discover=False)
    if args.agent_command == "doctor":
        result = check_agent_workflow(root)
        states = {"current": "一致", "missing": "缺失", "outdated": "已过期", "unsafe_symlink": "符号链接（拒绝读取）", "unreadable": "无法读取"}
        human = "Agent 工作流指引均为当前版本。" if result["ok"] else "需要检查：" + ", ".join(f"{item['path']}（{states[item['status']]}）" for item in result["files"])
        emit(args, result, human, error=not result["ok"])
        return 0 if result["ok"] else 1
    result = install_agent_workflow(root)
    emit(
        args, result,
        "已安装：" + (", ".join(result["installed"]) or "无")
        + ("；已保留现有文件：" + ", ".join(result["preserved"]) if result["preserved"] else ""),
    )
    return 0
