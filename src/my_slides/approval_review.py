"""Review packets and chat-confirmation phrases.

Chat approval records the user's reply and binds it to a content hash. It does
not prove, by itself, that the person typed that reply.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .dependencies import fingerprint_json
from .project import now
from .state import refresh_unit_currency
from .units import Unit, UnitsError, load_units_manifest, unit_paths


def approval_mode(cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("approval_mode") or "chat").strip()
    if mode not in {"chat", "terminal"}:
        raise ValueError("project.yaml 的 approval_mode 必须是 chat 或 terminal")
    return mode


def configured_reviewer(cfg: dict[str, Any]) -> str:
    return str(cfg.get("reviewer") or "").strip()


def confirmation_phrase(kind: str, target: str, digest: str) -> str:
    return f"APPROVE {kind.upper()} {target} {digest[:12]}"


def approval_binding(unit: Unit, kind: str, state: dict[str, Any]) -> dict[str, str]:
    """Fields a confirmation phrase must match, beyond the body hash.

    Chapter, report dependency fingerprint, and the Spec's bound report version
    are included so an older phrase cannot approve a moved section or a request
    resubmitted after dependencies changed.
    """
    pending = state[kind].get("pending_approval")
    if not isinstance(pending, dict):
        pending = {}
    binding = {
        "chapter": unit.chapter,
        "content_sha256": str(state[kind].get("content_sha256") or ""),
        "id": unit.id,
    }
    if kind == "report":
        binding["input_fingerprint"] = str(pending.get("input_fingerprint") or state["report"].get("input_fingerprint") or "")
    else:
        binding["report_input_fingerprint"] = str(
            pending.get("report_input_fingerprint") or state["spec"].get("report_input_fingerprint") or ""
        )
        binding["report_sha256"] = str(pending.get("report_sha256") or state["spec"].get("report_sha256") or "")
    return binding


def bindings_digest(bindings: list[dict[str, str]], *, chapter_scope: bool) -> str:
    ordered = sorted(bindings, key=lambda item: item["id"])
    if chapter_scope:
        return fingerprint_json(ordered)
    return fingerprint_json(ordered[0])


def approved_copy_path(base: Path, kind: str, unit_id: str, sha: str) -> Path:
    return base / ".state" / "approved" / kind / unit_id / f"{sha}.md"


def archive_approved_copy(base: Path, kind: str, unit_id: str, sha: str, text: str) -> None:
    path = approved_copy_path(base, kind, unit_id, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(text, encoding="utf-8")


DIFF_LINE_LIMIT = 40


def _unified_diff(previous: str, current: str, label: str) -> tuple[str, bool]:
    diff = list(difflib.unified_diff(
        previous.splitlines(),
        current.splitlines(),
        fromfile=f"{label}（已批准）",
        tofile=f"{label}（待审批）",
        lineterm="",
    ))
    if len(diff) <= DIFF_LINE_LIMIT:
        return "\n".join(diff), False
    notice = f"… 差异已截断，仅显示前 {DIFF_LINE_LIMIT} 行。完整待审正文见下方。"
    return "\n".join([*diff[:DIFF_LINE_LIMIT], notice]), True


def _spec_change_diff(previous: str, current: str) -> tuple[str, list[str], bool]:
    from .unit_workflow import split_spec_pages

    old_preamble, old_pages = split_spec_pages(previous)
    new_preamble, new_pages = split_spec_pages(current)
    old_map = {page["number"]: page["body"] for page in old_pages}
    new_map = {page["number"]: page["body"] for page in new_pages}
    notes: list[str] = []
    chunks: list[str] = []
    truncated = False
    if old_preamble.strip() != new_preamble.strip():
        notes.append("文首：修改")
        text, cut = _unified_diff(old_preamble, new_preamble, "文首")
        chunks.append(text)
        truncated = truncated or cut
    for number in sorted(set(old_map) | set(new_map)):
        old_body = old_map.get(number)
        new_body = new_map.get(number)
        if old_body is None and new_body is not None:
            notes.append(f"第 {number} 页：新增")
            text, cut = _unified_diff("", new_body, f"第 {number} 页")
        elif new_body is None and old_body is not None:
            notes.append(f"第 {number} 页：删除")
            text, cut = _unified_diff(old_body, "", f"第 {number} 页")
        elif old_body != new_body:
            notes.append(f"第 {number} 页：修改")
            text, cut = _unified_diff(old_body or "", new_body or "", f"第 {number} 页")
        else:
            continue
        chunks.append(text)
        truncated = truncated or cut
    return "\n".join(chunk for chunk in chunks if chunk), notes, truncated


def describe_changes(kind: str, previous: str | None, current: str) -> dict[str, Any]:
    if previous is None:
        return {"summary": "没有可对比的已批准副本", "pages": [], "diff": "", "truncated": False}
    if previous == current:
        return {"summary": "与上次批准的内容相同", "pages": [], "diff": "", "truncated": False}
    if kind == "spec":
        diff, pages, truncated = _spec_change_diff(previous, current)
        summary = "；".join(pages) if pages else "Spec 有变化"
        if truncated:
            summary += "（差异已截断）"
        return {"summary": summary, "pages": pages, "diff": diff, "truncated": truncated}
    diff, truncated = _unified_diff(previous, current, "报告")
    summary = "报告正文有变化"
    if truncated:
        summary += "（差异已截断）"
    return {"summary": summary, "pages": [], "diff": diff, "truncated": truncated}


def select_review_units(
    base: Path,
    cfg: dict[str, Any],
    *,
    unit_id: str | None,
    chapter: str | None,
) -> tuple[list[Unit], str]:
    if bool(unit_id) == bool(chapter):
        raise ValueError("请指定 --unit 或 --chapter 其中之一")
    units, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        raise UnitsError("；".join(errors))
    if unit_id:
        match = next((unit for unit in units if unit.id == unit_id), None)
        if match is None:
            raise UnitsError(f"未知单元：{unit_id}")
        return [match], unit_id
    chosen = [unit for unit in units if unit.chapter == chapter]
    if not chosen:
        raise UnitsError(f"章节中没有小章节：{chapter}")
    return chosen, str(chapter)


def review_packet(
    base: Path,
    cfg: dict[str, Any],
    kind: str,
    *,
    unit_id: str | None,
    chapter: str | None,
    project_root: Path,
) -> dict[str, Any]:
    if kind not in {"report", "spec"}:
        raise ValueError(f"未知审批类型：{kind}")
    units, target = select_review_units(base, cfg, unit_id=unit_id, chapter=chapter)
    rows: list[dict[str, Any]] = []
    entries: list[dict[str, str]] = []
    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        if not state[kind]["pending_current"]:
            raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请；请先提交审批")
        path = unit_paths(base, unit.id).report if kind == "report" else unit_paths(base, unit.id).spec
        current = path.read_text(encoding="utf-8")
        previous_sha = state[kind].get("approved_sha256")
        previous = None
        if isinstance(previous_sha, str) and previous_sha:
            copy = approved_copy_path(base, kind, unit.id, previous_sha)
            if copy.is_file():
                previous = copy.read_text(encoding="utf-8")
        from .unit_workflow import split_spec_pages

        _preamble, pages = split_spec_pages(current) if kind == "spec" else ("", [])
        binding = approval_binding(unit, kind, state)
        entries.append(binding)
        rows.append({
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "path": path.relative_to(base).as_posix(),
            "sha256": binding["content_sha256"],
            "pages": len(pages) if kind == "spec" else None,
            "content": current,
            "changes": describe_changes(kind, previous, current),
        })
    digest = bindings_digest(entries, chapter_scope=not unit_id)
    phrase = confirmation_phrase(kind, target, digest)
    return {
        "kind": kind,
        "target": target,
        "scope": "unit" if unit_id else "chapter",
        "phrase": phrase,
        "digest": digest,
        "units": rows,
        "reviewed_at": now(),
    }


def confirm_chat(
    base: Path,
    cfg: dict[str, Any],
    kind: str,
    *,
    unit_id: str | None,
    chapter: str | None,
    phrase: str,
    user_reply: str,
    reviewer: str | None,
    when: str,
    project_root: Path,
) -> list[dict[str, Any]]:
    if approval_mode(cfg) != "chat":
        raise ValueError("当前项目的 approval_mode 是 terminal；请在交互终端运行 confirm，不能使用 --via chat")
    reply = user_reply.strip()
    if not reply:
        raise ValueError("需要传入用户在对话中的原话（--user-reply）")
    name = (reviewer or "").strip() or configured_reviewer(cfg)
    if not name:
        raise ValueError("请在 project.yaml 设置 reviewer，或传入 --reviewer")
    units, target = select_review_units(base, cfg, unit_id=unit_id, chapter=chapter)
    entries: list[dict[str, str]] = []
    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        if not state[kind]["pending_current"]:
            raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请，或申请后内容已变化；请重新运行 review")
        entries.append(approval_binding(unit, kind, state))
    digest = bindings_digest(entries, chapter_scope=not unit_id)
    expected = confirmation_phrase(kind, target, digest)
    if phrase.strip() != expected:
        raise ValueError("确认短语与当前待审批内容或上下文不一致；请重新运行 review")
    import getpass

    from .unit_workflow import confirm_unit_approval

    account = getpass.getuser()
    confirmed: list[dict[str, Any]] = []
    for unit in units:
        state = confirm_unit_approval(
            base, unit, kind, when=when, approved_by=name, approved_account=account,
            project_root=project_root, channel="chat", user_reply=reply,
        )
        confirmed.append({"id": unit.id, "approved_by": state[kind]["approved_by"], "channel": "chat"})
    return confirmed
