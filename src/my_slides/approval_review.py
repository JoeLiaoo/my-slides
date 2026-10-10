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


def batch_digest(entries: list[tuple[str, str]]) -> str:
    payload = [{"id": unit_id, "sha256": sha} for unit_id, sha in sorted(entries)]
    return fingerprint_json(payload)


def approved_copy_path(base: Path, kind: str, unit_id: str, sha: str) -> Path:
    return base / ".state" / "approved" / kind / unit_id / f"{sha}.md"


def archive_approved_copy(base: Path, kind: str, unit_id: str, sha: str, text: str) -> None:
    path = approved_copy_path(base, kind, unit_id, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(text, encoding="utf-8")


def _page_changes(previous: str, current: str) -> list[str]:
    from .unit_workflow import split_spec_pages

    _old_preamble, old_pages = split_spec_pages(previous)
    _new_preamble, new_pages = split_spec_pages(current)
    old_map = {page["number"]: page["body"] for page in old_pages}
    new_map = {page["number"]: page["body"] for page in new_pages}
    notes: list[str] = []
    for number in sorted(set(old_map) | set(new_map)):
        if number not in old_map:
            notes.append(f"第 {number} 页：新增")
        elif number not in new_map:
            notes.append(f"第 {number} 页：删除")
        elif old_map[number] != new_map[number]:
            notes.append(f"第 {number} 页：修改")
    return notes


def describe_changes(kind: str, previous: str | None, current: str) -> dict[str, Any]:
    if previous is None:
        return {"summary": "没有可对比的已批准副本", "pages": [], "diff": ""}
    if previous == current:
        return {"summary": "与上次批准的内容相同", "pages": [], "diff": ""}
    if kind == "spec":
        pages = _page_changes(previous, current)
        return {"summary": "；".join(pages) if pages else "Spec 有变化", "pages": pages, "diff": ""}
    diff = list(difflib.unified_diff(previous.splitlines(), current.splitlines(), lineterm="", n=1))
    return {
        "summary": "报告正文有变化",
        "pages": [],
        "diff": "\n".join(diff[:40]),
    }


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
    entries: list[tuple[str, str]] = []
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
        digest = str(state[kind]["content_sha256"])
        entries.append((unit.id, digest))
        rows.append({
            "id": unit.id,
            "chapter": unit.chapter,
            "title": unit.title,
            "path": path.relative_to(base).as_posix(),
            "sha256": digest,
            "pages": len(pages) if kind == "spec" else None,
            "changes": describe_changes(kind, previous, current),
        })
    digest = entries[0][1] if unit_id else batch_digest(entries)
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
    entries: list[tuple[str, str]] = []
    for unit in units:
        state = refresh_unit_currency(base, unit, project_root=project_root)
        if not state[kind]["pending_current"]:
            raise UnitsError(f"{unit.id}：没有有效的 {kind} 待审批申请，或申请后内容已变化；请重新运行 review")
        entries.append((unit.id, str(state[kind]["content_sha256"])))
    digest = entries[0][1] if unit_id else batch_digest(entries)
    expected = confirmation_phrase(kind, target, digest)
    if phrase.strip() != expected:
        raise ValueError("确认短语与当前待审批内容不一致；请重新运行 review")
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
