"""User revokes an existing approval.

Same gate as ``confirm``/``reject``: chat mode requires ``--via chat`` with
``--phrase`` and ``--user-reply``; terminal mode requires an interactive TTY.
Approved copies are kept in ``.state/approved/`` for history.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Any

from ..approval_review import bindings_digest, revoke_binding, revoke_chat, revoke_phrase
from ..command_output import emit
from ..project import ensure_project, now, project_root, require_v2_project
from ..state import refresh_unit_currency
from ..unit_workflow import resolve_unit_selection, revoke_unit_approval


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    via = getattr(args, "via", None)
    chapter = getattr(args, "chapter", None)
    reason = (getattr(args, "reason", "") or "").strip()
    units = resolve_unit_selection(
        base, cfg,
        unit_ids=[getattr(args, "unit", None)] if getattr(args, "unit", None) else None,
        changed=False, all_units=False, chapter=chapter,
    )
    if via == "chat":
        phrase_value = (getattr(args, "phrase", "") or "").strip()
        user_reply_value = (getattr(args, "user_reply", "") or "").strip()
        if not phrase_value or not user_reply_value:
            # Print (and in --json return) the approved version info and the
            # REVOKE phrase the user must agree to. Recording nothing keeps
            # this a read-only preview step.
            target = chapter if chapter else (getattr(args, "unit", None) or "")
            entries: list[dict[str, str]] = []
            approved_rows: list[dict[str, Any]] = []
            for unit in units:
                state = refresh_unit_currency(base, unit, project_root=root)
                approved_sha = state[args.kind].get("approved_sha256")
                if not approved_sha:
                    raise ValueError(f"{unit.id}：{args.kind} 还没有用户批准的当前版本；无需撤回")
                entries.append(revoke_binding(unit, args.kind, state))
                approved_rows.append({
                    "id": unit.id,
                    "chapter": unit.chapter,
                    "title": unit.title,
                    "approved_sha256": approved_sha,
                    "approved_at": state[args.kind].get("approved_at"),
                    "approved_by": state[args.kind].get("approved_by"),
                    "approved_account": state[args.kind].get("approved_account"),
                    "approval_channel": state[args.kind].get("approval_channel"),
                })
            digest = bindings_digest(entries, chapter_scope=not getattr(args, "unit", None))
            phrase = revoke_phrase(args.kind, target, digest)
            data = {
                "kind": args.kind,
                "decision": "revoke-preview",
                "channel": "chat",
                "reason": reason or None,
                "phrase": phrase,
                "units": approved_rows,
            }
            human_lines = [f"待撤回批准：{args.kind} / {target}"]
            for row in approved_rows:
                human_lines.append(
                    f"\n{row['chapter']} / {row['title']}（{row['id']}）\n"
                    f"批准人：{row['approved_by']}（{row['approved_account']}）\n"
                    f"批准时间：{row['approved_at']}\n"
                    f"通道：{row['approval_channel']}\n"
                    f"已批准 SHA-256：{row['approved_sha256']}"
                )
            human_lines.append(f"\n确认短语：{phrase}")
            human_lines.append("用户需在对话中明确表示要撤回该批准。Agent 再用 --phrase 和 --user-reply 执行一次；不得自动提交。")
            emit(args, data, "\n".join(human_lines))
            return 0
        decisions = revoke_chat(
            base, cfg, args.kind,
            unit_id=getattr(args, "unit", None), chapter=chapter,
            phrase=phrase_value,
            user_reply=user_reply_value,
            reviewer=getattr(args, "reviewer", None),
            reason=reason,
            when=now(), project_root=root,
        )
        data = {
            "kind": args.kind,
            "decision": "revoked",
            "channel": "chat",
            "reason": reason or None,
            "units": decisions,
        }
        names = "、".join(item["id"] for item in decisions)
        emit(args, data, f"已通过对话撤回 {args.kind} 批准：{names}")
        return 0

    if chapter:
        raise ValueError("整章撤回请使用 --via chat；交互终端一次只撤回一个小章节")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("撤回批准必须由用户在交互终端执行；不能通过管道、--json 或非交互脚本撤回")
    if not getattr(args, "unit", None):
        raise ValueError("请指定 --unit")
    unit = units[0]
    state = refresh_unit_currency(base, unit, project_root=root)
    approved_sha = state[args.kind].get("approved_sha256")
    if not approved_sha:
        raise ValueError(f"{unit.id}：{args.kind} 还没有用户批准的当前版本；无需撤回")
    entries = [revoke_binding(unit, args.kind, state)]
    digest = bindings_digest(entries, chapter_scope=False)
    label = revoke_phrase(args.kind, unit.id, digest)
    print(
        f"待撤回批准：{args.kind} / {unit.id}\n"
        f"SHA-256：{approved_sha}\n"
        f"原因：{reason or '（未提供原因）'}"
    )
    reviewer = input("审批人姓名：").strip()
    if not reviewer:
        raise ValueError("审批人姓名不能为空；未记录撤回")
    if input(f"确认要撤回该批准？输入 {label} 确认：").strip() != label:
        raise ValueError("确认文字不匹配；未记录撤回")
    state = revoke_unit_approval(
        base, unit, args.kind,
        when=now(), reason=reason or None,
        revoked_by=reviewer,
        revoked_account=getpass.getuser(),
        project_root=root, channel="terminal",
    )
    print(f"已撤回 {args.kind} / {unit.id} 的批准")
    return 0