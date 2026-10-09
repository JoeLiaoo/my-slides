"""Create Wiki and per-unit agent handoff files."""
from __future__ import annotations

import argparse
from datetime import datetime

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..sources import scan_sources
from ..unit_workflow import prepare_unit_handoff, resolve_unit_selection
from ..wiki import snapshot_wiki, validate_wiki


def prepare(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    kind = args.kind
    if kind in {"report", "spec", "slides"}:
        units = resolve_unit_selection(
            base,
            cfg,
            unit_ids=getattr(args, "units", None),
            changed=bool(getattr(args, "changed", False)),
            all_units=bool(getattr(args, "all_units", False)),
        )
        if kind == "report":
            _, pending, removed = scan_sources(root, base, cfg)
            if pending or removed:
                raise ValueError("请先整理有变化或已移除的资料，并运行 my-slides sources mark-ingested")
            wiki_errors = validate_wiki(base, cfg)
            if wiki_errors:
                raise ValueError("请先修复 Wiki 链接：" + "；".join(wiki_errors))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        if kind == "report":
            snapshot_wiki(base, stamp)
        output = prepare_unit_handoff(base, root, units, kind, stamp=stamp)
        emit(
            args,
            {"task_file": str(output), "kind": kind, "units": [u.id for u in units], "deprecated": False},
            f"已生成单元交接材料：{output}",
        )
        return 0
    out_dir = base / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = out_dir / f"{stamp}-{kind}.md"
    chapters = cfg.get("chapters", [])
    common = f"项目目录：{root}\n工作区：{base}\n章节顺序：" + "、".join(chapters)
    if kind == "wiki":
        if args.question:
            body = f"""# Wiki 问答任务

{common}

## 用户问题
{args.question}

先阅读 wiki/README.md 和 wiki/index.md，按索引找到相关页面并核对内容，再综合回答。回答中的结论应附上相关 Wiki 页面或原始资料链接；说明来源之间存在的差异和未解决的问题。只在用户明确要求沉淀时才新建或更新 Wiki 页面，并同步维护 index.md 和 log.md。
"""
        else:
            _, pending, removed = scan_sources(root, base, cfg)
            todo = "\n".join(f"- {p}" for p in pending) or "- 当前没有新增或修改的 Markdown 资料。"
            gone = "\n".join(f"- {p}" for p in removed) or "- 无。"
            body = f"""# Wiki 整理任务

{common}

先阅读 wiki/README.md、wiki/index.md 和近期 wiki/log.md。按 Karpathy LLM Wiki 的方式把新增资料整合进已有主题页，维护页面间链接、按章节更新 index，并向 log 追加记录。使用普通 Markdown 与可读链接，不添加固定标签、frontmatter 或来源 ID。链接项目根目录下的源资料时，按源文件所在 Wiki 页面的位置计算相对路径。完成后运行 my-slides sources mark-ingested。

## 待整理资料
{todo}

## 已删除或移出扫描范围的资料
{gone}

原始资料保持只读。若资料之间存在口径冲突，在相关页面用自然语言记下差异和待核实问题。
"""
    else:
        raise ValueError(f"未知 prepare 类型：{kind}")
    output.write_text(body, encoding="utf-8")
    emit(args, {"task_file": str(output), "kind": kind, "deprecated": False}, f"已生成交接材料：{output}")
    return 0
