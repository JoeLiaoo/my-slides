"""Safe structural operations for the v2 unit manifest."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dependencies import UNIT_DEPS_FILENAME, build_unit_dependency_graph, fingerprint_file, load_explicit_unit_deps
from .project import now
from .state import read_unit_state, refresh_unit_currency, write_unit_state
from .units import (
    Unit,
    UnitsError,
    dump_units_manifest,
    encode_link_path,
    iter_local_markdown_targets,
    load_units_manifest,
    MARKDOWN_LINK_RE,
    MARKDOWN_REF_DEF_RE,
    resolve_local_markdown_path,
    strip_markdown_link_target,
    unit_paths,
    validate_units,
)

TRASH_DIR = Path(".state/trash")


def _trash_root(base: Path) -> Path:
    root = base / TRASH_DIR
    if root.is_symlink():
        raise UnitsError("回收区不能是符号链接")
    try:
        root.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise UnitsError("回收区路径越出工作区") from exc
    return root


def _manifest(base: Path, chapters: list[str]) -> list[Unit]:
    units, errors = load_units_manifest(base, chapters)
    if errors:
        raise UnitsError("；".join(errors))
    return units


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_manifest_atomic(base: Path, units: list[Unit], chapters: list[str]) -> None:
    errors = validate_units(units, chapters)
    if errors:
        raise UnitsError("；".join(errors))
    path = base / "units.json"
    tmp = path.with_name("units.json.tmp")
    tmp.write_text(dump_units_manifest(units), encoding="utf-8")
    tmp.replace(path)


def _safe_project_path(base: Path, relative: str) -> Path:
    path = base / relative
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise UnitsError(f"操作路径越出工作区：{relative}") from exc
    return path


def _ensure_within_workspace(base: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise UnitsError(f"操作路径越出工作区：{path}") from exc


def _unit_artifacts(base: Path, unit_id: str) -> list[Path]:
    paths = unit_paths(base, unit_id)
    candidates = [
        paths.report,
        paths.spec,
        paths.page,
        paths.preview,
        paths.state,
        paths.report.with_name(f"{unit_id}.{UNIT_DEPS_FILENAME}"),
    ]
    existing = []
    for path in candidates:
        if path.is_symlink():
            raise UnitsError(f"不支持单元产物为符号链接：{path}")
        if path.exists() or path.is_symlink():
            try:
                path.resolve().relative_to(base.resolve())
            except ValueError as exc:
                raise UnitsError(f"单元产物路径越出工作区：{path}") from exc
        if path.is_file():
            existing.append(path)
    return existing


def _invalidate_deck_checks(base: Path, units: list[Unit]) -> None:
    """Force every unit's browser result stale after a structural inventory change."""
    for unit in units:
        path = unit_paths(base, unit.id).state
        _ensure_within_workspace(base, path)
        if path.is_symlink():
            raise UnitsError(f"不支持单元状态文件为符号链接：{path}")
        state = read_unit_state(base, unit.id)
        state["check"]["input_fingerprint"] = None
        state["check"]["current"] = False
        write_unit_state(base, unit.id, state)


def _snapshot_unit_states(base: Path, units: list[Unit]) -> dict[Path, bytes | None]:
    snapshots: dict[Path, bytes | None] = {}
    for unit in units:
        path = unit_paths(base, unit.id).state
        _ensure_within_workspace(base, path)
        if path.is_symlink():
            raise UnitsError(f"不支持单元状态文件为符号链接：{path}")
        snapshots[path] = path.read_bytes() if path.is_file() else None
    return snapshots


def _restore_unit_states(snapshots: dict[Path, bytes | None]) -> None:
    for path, content in snapshots.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _unit_refs(
    base: Path,
    unit_id: str,
    units: list[Unit],
    *,
    project_root: Path | None = None,
) -> dict[str, list[str]]:
    dependents: list[str] = []
    graph = build_unit_dependency_graph(base, units)
    for source, dependencies in graph.items():
        if unit_id in dependencies:
            dependents.append(source)

    target_paths = {
        path.resolve()
        for path in (
            unit_paths(base, unit_id).report,
            unit_paths(base, unit_id).spec,
            unit_paths(base, unit_id).page,
            unit_paths(base, unit_id).preview,
        )
    }
    markdown_links: list[str] = []
    external_markdown_links: list[str] = []
    scan_root = (project_root or base.parent).resolve()
    base_resolved = base.resolve()
    excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    for path in scan_root.rglob("*.md"):
        try:
            project_relative = path.relative_to(scan_root)
        except ValueError:
            continue
        if path.is_symlink() or any(part.startswith(".") or part in excluded_dirs for part in project_relative.parts):
            continue
        # The assembled report is a derived snapshot; it is rebuilt after inventory changes.
        if path.resolve() == (base / "reports" / "report.md").resolve():
            continue
        try:
            targets = iter_local_markdown_targets(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        for target in targets:
            resolved = resolve_local_markdown_path(target, path)
            if resolved in target_paths:
                try:
                    displayed = path.relative_to(base_resolved).as_posix()
                except ValueError:
                    displayed = project_relative.as_posix()
                markdown_links.append(displayed)
                if not path.resolve().is_relative_to(base.resolve()):
                    external_markdown_links.append(displayed)
                break
    return {
        "dependent_units": sorted(dependents),
        "markdown_references": sorted(set(markdown_links)),
        "external_markdown_references": sorted(set(external_markdown_links)),
    }


def remove_plan(
    base: Path,
    unit_id: str,
    chapters: list[str],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    _trash_root(base)
    units = _manifest(base, chapters)
    index = next((i for i, unit in enumerate(units) if unit.id == unit_id), None)
    if index is None:
        raise UnitsError(f"未知单元：{unit_id}")
    unit = units[index]
    state = refresh_unit_currency(base, unit, project_root=base.parent)
    refs = _unit_refs(base, unit_id, units, project_root=project_root)
    blockers = []
    if unit.role == "cover":
        blockers.append("cover 单元不能删除")
    if refs["dependent_units"]:
        blockers.append("仍有单元声明依赖此单元")
    if refs["markdown_references"]:
        blockers.append("仍有 Markdown 链接指向此单元")
    artifacts = _unit_artifacts(base, unit_id)
    paths = unit_paths(base, unit_id)
    expected = [
        (paths.report, "report"),
        (paths.spec, "spec"),
        (paths.page, "page"),
        (paths.preview, "preview"),
        (paths.state, "state"),
        (paths.report.with_name(f"{unit_id}.{UNIT_DEPS_FILENAME}"), "dependency"),
    ]
    return {
        "operation": "remove",
        "unit": unit.to_dict(),
        "position": index,
        "files": [path.relative_to(base).as_posix() for path in artifacts],
        "artifacts": [
            {"path": path.relative_to(base).as_posix(), "kind": kind, "exists": path.is_file()}
            for path, kind in expected
        ],
        "approvals": {
            "report": {"current": bool(state["report"].get("current")), "pending": bool(state["report"].get("pending_current")), "has_record": bool(state["report"].get("approved_sha256")), "approved_by": state["report"].get("approved_by")},
            "spec": {"current": bool(state["spec"].get("current")), "pending": bool(state["spec"].get("pending_current")), "has_record": bool(state["spec"].get("approved_sha256")), "approved_by": state["spec"].get("approved_by")},
        },
        "dependencies": {
            "declared": load_explicit_unit_deps(base, unit_id),
            "dependent_units": refs["dependent_units"],
            "markdown_references": refs["markdown_references"],
            "external_markdown_references": refs["external_markdown_references"],
        },
        "blocked": bool(blockers),
        "blockers": blockers,
        "deck_requires_rebuild": True,
        "affected_outputs": ["reports/report.md（原文件保留，但内容可能过期）", "slides/index.html（原文件保留，但需要重建并重查）"],
        "requires_user_consent": bool(state["report"].get("approved_sha256") or state["spec"].get("approved_sha256")),
        "trash_location": f"{TRASH_DIR.as_posix()}/<timestamp>-{unit_id}",
    }


def remove_unit(
    base: Path,
    unit_id: str,
    chapters: list[str],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    plan = remove_plan(base, unit_id, chapters, project_root=project_root)
    if plan["blocked"]:
        raise UnitsError("无法删除：" + "；".join(plan["blockers"]))
    units = _manifest(base, chapters)
    index = plan["position"]
    del units[index]
    errors = validate_units(units, chapters)
    if errors:
        raise UnitsError("删除会使单元清单无效：" + "；".join(errors))
    manifest_path = base / "units.json"
    manifest_backup = manifest_path.read_bytes()
    state_backups = _snapshot_unit_states(base, units)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    trash_id = f"{stamp}-{unit_id}"
    trash = _trash_root(base) / trash_id
    artifacts = _unit_artifacts(base, unit_id)
    data_dir = trash / "data"
    data_dir.mkdir(parents=True, exist_ok=False)
    moved: list[tuple[Path, Path]] = []
    records = []
    try:
        for source in artifacts:
            relative = source.relative_to(base).as_posix()
            target = data_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            moved.append((target, source))
            records.append({"original_path": relative, "trash_path": target.relative_to(trash).as_posix(), "sha256": fingerprint_file(target)})
        _atomic_json(
            trash / "manifest.json",
            {
                "trash_id": trash_id,
                "removed_at": now(),
                "unit": plan["unit"],
                "position": index,
                "artifacts": records,
            },
        )
        _write_manifest_atomic(base, units, chapters)
        _invalidate_deck_checks(base, units)
    except Exception:
        for source, destination in reversed(moved):
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                source.replace(destination)
        shutil.rmtree(trash, ignore_errors=True)
        manifest_path.write_bytes(manifest_backup)
        _restore_unit_states(state_backups)
        raise
    result = dict(plan)
    result.update({
        "removed": True,
        "trash_id": trash_id,
        "trash_location": (base / TRASH_DIR / trash_id).relative_to(base).as_posix(),
        "restore_command": f"my-slides units restore {trash_id}",
    })
    return result


def list_trash(base: Path) -> list[dict[str, Any]]:
    root = _trash_root(base)
    rows = []
    if not root.is_dir():
        return rows
    for manifest_path in sorted(root.glob("*/manifest.json"), reverse=True):
        if manifest_path.parent.is_symlink():
            continue
        if manifest_path.is_symlink():
            continue
        try:
            manifest_path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("restored_at"):
            continue
        rows.append({
            "trash_id": data.get("trash_id", manifest_path.parent.name),
            "unit": data.get("unit", {}),
            "removed_at": data.get("removed_at"),
            "position": data.get("position"),
            "files": [item.get("original_path") for item in data.get("artifacts", [])],
            "restore_command": f"my-slides units restore {data.get('trash_id', manifest_path.parent.name)}",
        })
    return rows


def restore_unit(base: Path, trash_id: str, chapters: list[str]) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8}T\d{12}Z-[a-z0-9]+(?:-[a-z0-9]+)*", trash_id):
        raise UnitsError("回收记录 ID 无效")
    trash = _trash_root(base) / trash_id
    manifest_path = trash / "manifest.json"
    if manifest_path.is_symlink():
        raise UnitsError(f"回收记录不能是符号链接：{trash_id}")
    if not manifest_path.is_file():
        raise UnitsError(f"找不到回收记录：{trash_id}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnitsError(f"回收记录损坏：{trash_id}") from exc
    entry = data.get("unit")
    if not isinstance(entry, dict):
        raise UnitsError(f"回收记录缺少原始单元条目：{trash_id}")
    try:
        unit = Unit(**entry)
    except TypeError as exc:
        raise UnitsError(f"回收记录中的单元条目无效：{trash_id}") from exc
    if not trash_id.endswith("-" + unit.id):
        raise UnitsError("回收记录 ID 与单元 ID 不匹配")
    if trash.is_symlink():
        raise UnitsError("回收记录目录不能是符号链接")
    try:
        trash.resolve().relative_to(_trash_root(base).resolve())
    except ValueError as exc:
        raise UnitsError("回收记录路径越出回收区") from exc
    units = _manifest(base, chapters)
    if any(existing.id == unit.id for existing in units):
        raise UnitsError(f"单元 ID 已被占用，无法恢复：{unit.id}")
    position = data.get("position")
    if not isinstance(position, int) or position < 0 or position > len(units):
        raise UnitsError(f"回收记录中的原始位置无效：{position!r}")
    restored_units = list(units)
    restored_units.insert(position, unit)
    errors = validate_units(restored_units, chapters)
    if errors:
        raise UnitsError("无法按原位置恢复：" + "；".join(errors))
    _snapshot_unit_states(base, restored_units)

    allowed_paths = {
        path.relative_to(base).as_posix()
        for path in (
            unit_paths(base, unit.id).report,
            unit_paths(base, unit.id).spec,
            unit_paths(base, unit.id).page,
            unit_paths(base, unit.id).preview,
            unit_paths(base, unit.id).state,
            unit_paths(base, unit.id).report.with_name(f"{unit.id}.{UNIT_DEPS_FILENAME}"),
        )
    }
    records = data.get("artifacts", [])
    if not isinstance(records, list):
        raise UnitsError(f"回收记录中的产物清单无效：{trash_id}")
    moves: list[tuple[Path, Path]] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("original_path"), str) or not isinstance(record.get("trash_path"), str):
            raise UnitsError(f"回收记录中的产物条目无效：{trash_id}")
        original_relative = str(record["original_path"])
        if original_relative not in allowed_paths:
            raise UnitsError(f"回收记录含有非单元产物路径：{original_relative}")
        original = _safe_project_path(base, original_relative)
        source = trash / str(record["trash_path"])
        try:
            source.resolve().relative_to(trash.resolve())
        except ValueError as exc:
            raise UnitsError(f"回收文件路径越界：{record['trash_path']}") from exc
        if original.exists() or original.is_symlink():
            raise UnitsError(f"恢复目标已存在，不会覆盖：{record['original_path']}")
        if source.is_symlink() or not source.is_file():
            raise UnitsError(f"回收文件缺失：{record['trash_path']}")
        moves.append((source, original))
    completed: list[tuple[Path, Path]] = []
    units_manifest = base / "units.json"
    units_manifest_backup = units_manifest.read_bytes()
    try:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            completed.append((destination, source))
        _write_manifest_atomic(base, restored_units, chapters)
        state = refresh_unit_currency(base, unit, project_root=base.parent)
        data["restored_at"] = now()
        _atomic_json(manifest_path, data)
    except Exception:
        for destination, source in reversed(completed):
            source.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.replace(source)
        units_manifest.write_bytes(units_manifest_backup)
        raise
    _invalidate_deck_checks(base, restored_units)
    return {
        "restored": True,
        "trash_id": trash_id,
        "unit": unit.to_dict(),
        "position": position,
        "approvals": {"report": state["report"]["current"], "spec": state["spec"]["current"]},
        "invalidated": [kind for kind in ("report", "spec") if not state[kind]["current"]],
    }


def _insert_index(units: list[Unit], chapter: str, chapters: list[str], after: str | None) -> int:
    chapter_index = chapters.index(chapter)
    if after is not None:
        index = next((i for i, unit in enumerate(units) if unit.id == after), None)
        if index is None:
            raise UnitsError(f"--after 指定的单元不存在：{after}")
        if units[index].chapter != chapter:
            raise UnitsError("--after 必须与新单元位于同一章节")
        return index + 1
    same = [i for i, unit in enumerate(units) if unit.chapter == chapter]
    if same:
        return same[-1] + 1
    later = [i for i, unit in enumerate(units) if chapters.index(unit.chapter) > chapter_index]
    return min(later) if later else len(units)


def add_unit(base: Path, unit_id: str, chapter: str, chapters: list[str], *, after: str | None = None, role: str = "content") -> dict[str, Any]:
    units = _manifest(base, chapters)
    if any(unit.id == unit_id for unit in units):
        raise UnitsError(f"单元 ID 已存在：{unit_id}")
    if chapter not in chapters:
        raise UnitsError(f"章节不存在于 project.yaml：{chapter}")
    if role != "content":
        raise UnitsError("units add 只能新增 content 单元；cover 是唯一且固定在首位")
    index = _insert_index(units, chapter, chapters, after)
    new_unit = Unit(id=unit_id, chapter=chapter, role=role)
    proposed = list(units)
    proposed.insert(index, new_unit)
    errors = validate_units(proposed, chapters)
    if errors:
        raise UnitsError("新增会使单元清单无效：" + "；".join(errors))
    paths = unit_paths(base, unit_id)
    targets = [
        paths.report,
        paths.spec,
        paths.page,
        paths.preview,
        paths.state,
        paths.report.with_name(f"{unit_id}.{UNIT_DEPS_FILENAME}"),
    ]
    if any(path.exists() or path.is_symlink() for path in targets):
        raise UnitsError("新单元目标文件已存在，不会覆盖")
    for path in targets:
        _ensure_within_workspace(base, path)
    manifest_path = base / "units.json"
    manifest_backup = manifest_path.read_bytes()
    state_backups = _snapshot_unit_states(base, proposed)
    created: list[Path] = []
    try:
        for path in targets[:3]:
            path.parent.mkdir(parents=True, exist_ok=True)
        paths.report.write_text(f"# {unit_id}\n\n<!-- TODO: 撰写 {chapter} 的报告内容。 -->\n", encoding="utf-8")
        created.append(paths.report)
        paths.spec.write_text(f"# {unit_id}\n\n页面 ID：{unit_id}\n页面角色：content\n\n<!-- TODO: 编写一页 Spec。 -->\n", encoding="utf-8")
        created.append(paths.spec)
        paths.page.write_text(f'<section class="slide" data-unit-id="{unit_id}" data-page-role="content">\n  <!-- TODO: 实现页面。 -->\n</section>\n', encoding="utf-8")
        created.append(paths.page)
        _write_manifest_atomic(base, proposed, chapters)
        _invalidate_deck_checks(base, proposed)
    except Exception:
        manifest_path.write_bytes(manifest_backup)
        _restore_unit_states(state_backups)
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {"added": True, "unit": new_unit.to_dict(), "position": index, "files": [p.relative_to(base).as_posix() for p in targets[:3]]}


def _place_moved_unit(
    remaining: list[Unit],
    moved: Unit,
    chapters: list[str],
    *,
    after: str | None,
    before: str | None,
) -> None:
    if after is not None and before is not None:
        raise UnitsError("--after 与 --before 只能二选一")
    if after == moved.id or before == moved.id:
        raise UnitsError("不能相对自身定位")
    if after is not None:
        after_index = next((i for i, unit in enumerate(remaining) if unit.id == after), None)
        if after_index is None:
            raise UnitsError(f"--after 指定的单元不存在：{after}")
        if remaining[after_index].chapter != moved.chapter:
            raise UnitsError("--after 单元必须属于目标章节")
        remaining.insert(after_index + 1, moved)
        return
    if before is not None:
        before_index = next((i for i, unit in enumerate(remaining) if unit.id == before), None)
        if before_index is None:
            raise UnitsError(f"--before 指定的单元不存在：{before}")
        if remaining[before_index].chapter != moved.chapter:
            raise UnitsError("--before 单元必须属于目标章节")
        remaining.insert(before_index, moved)
        return
    remaining.insert(_insert_index(remaining, moved.chapter, chapters, None), moved)


def move_unit(
    base: Path,
    unit_id: str,
    chapters: list[str],
    *,
    after: str | None = None,
    before: str | None = None,
    chapter: str | None = None,
) -> dict[str, Any]:
    units = _manifest(base, chapters)
    index = next((i for i, unit in enumerate(units) if unit.id == unit_id), None)
    if index is None:
        raise UnitsError(f"未知单元：{unit_id}")
    old = units[index]
    before_state = refresh_unit_currency(base, old, project_root=base.parent)
    destination_chapter = chapter or old.chapter
    if destination_chapter not in chapters:
        raise UnitsError(f"章节不存在于 project.yaml：{destination_chapter}")
    remaining = [unit for unit in units if unit.id != unit_id]
    moved = Unit(id=old.id, chapter=destination_chapter, role=old.role)
    _place_moved_unit(remaining, moved, chapters, after=after, before=before)
    errors = validate_units(remaining, chapters)
    if errors:
        raise UnitsError("移动会使单元清单无效：" + "；".join(errors))
    manifest_path = base / "units.json"
    manifest_backup = manifest_path.read_bytes()
    state_backups = _snapshot_unit_states(base, remaining)
    try:
        _write_manifest_atomic(base, remaining, chapters)
        _invalidate_deck_checks(base, remaining)
        state = read_unit_state(base, unit_id)
        reconfirmation_from = None
        if old.chapter != destination_chapter:
            if before_state["report"].get("reconfirmation_required") and before_state["report"].get("pending_current"):
                previous_context = str(before_state["report"].get("reconfirmation_context") or "")
                if previous_context.startswith("章节：") and " → " in previous_context:
                    reconfirmation_from = previous_context[len("章节："):].split(" → ", 1)[0]
            elif before_state["report"].get("current"):
                reconfirmation_from = old.chapter
        if reconfirmation_from is not None:
            sha = fingerprint_file(unit_paths(base, unit_id).report)
            from .state import compute_report_input_fingerprint

            input_fp = compute_report_input_fingerprint(base, moved, project_root=base.parent) if sha else None
            state["report"]["reconfirmation_required"] = True
            state["report"]["reconfirmation_context"] = f"章节：{reconfirmation_from} → {destination_chapter}，内容未变"
            state["report"]["pending_approval"] = {
                "requested_at": now(),
                "content_sha256": sha,
                "input_fingerprint": input_fp,
                "review_context": state["report"]["reconfirmation_context"],
            }
            state["report"]["pending_current"] = bool(sha and input_fp)
        elif old.chapter != destination_chapter and state["report"].get("reconfirmation_required"):
            state["report"]["reconfirmation_required"] = False
            state["report"]["reconfirmation_context"] = None
            pending = state["report"].get("pending_approval")
            if isinstance(pending, dict) and pending.get("review_context"):
                state["report"]["pending_approval"] = None
        state["check"]["input_fingerprint"] = None
        state["check"]["current"] = False
        write_unit_state(base, unit_id, state)
        refreshed = refresh_unit_currency(base, moved, project_root=base.parent)
        if "单元顺序或章节发生变化，需重新构建整套 Slides 并检查" not in refreshed["reasons"]:
            refreshed["reasons"].append("单元顺序或章节发生变化，需重新构建整套 Slides 并检查")
        write_unit_state(base, unit_id, refreshed)
    except Exception:
        manifest_path.write_bytes(manifest_backup)
        _restore_unit_states(state_backups)
        raise
    return {
        "moved": True,
        "unit": moved.to_dict(),
        "from": {"chapter": old.chapter, "position": index},
        "to": {"chapter": destination_chapter, "position": next(i for i, unit in enumerate(remaining) if unit.id == unit_id)},
        "cross_chapter": old.chapter != destination_chapter,
        "report_reconfirmation": (refreshed["report"].get("reconfirmation_context") if refreshed["report"].get("reconfirmation_required") else None),
        "spec_approval_preserved": bool(refreshed["spec"].get("current")),
        "deck_requires_rebuild": True,
    }


def _rewrite_identity_text(text: str, old: str, new: str, *, kind: str) -> str:
    if kind == "spec":
        text = re.sub(r"^#\s+" + re.escape(old) + r"\s*$", f"# {new}", text, count=1, flags=re.MULTILINE)
        text = re.sub(r"^(##\s+Slide\s+\d+\s+[—-]\s*)" + re.escape(old) + r"\s*$", rf"\g<1>{new}", text, flags=re.MULTILINE)
        text = re.sub(r"^(页面 ID\s*[：:]\s*)" + re.escape(old) + r"(\s*)$", rf"\g<1>{new}\2", text, flags=re.MULTILINE)
    elif kind == "report":
        text = re.sub(r"^#\s+" + re.escape(old) + r"\s*$", f"# {new}", text, count=1, flags=re.MULTILINE)
    elif kind == "page":
        text = re.sub(r'(?<=data-unit-id=")[^" ]+(?=")', lambda m: new if m.group(0) == old else m.group(0), text)
        text = re.sub(r"(?<=data-unit-id=')[^' ]+(?=')", lambda m: new if m.group(0) == old else m.group(0), text)
        text = re.sub(r'(?<=id=")[^" ]+(?=")', lambda m: new if m.group(0) == old else m.group(0), text)
    return text


def _renamed_link_target(raw: str, source: Path, old_path: Path, new_path: Path) -> str | None:
    cleaned = strip_markdown_link_target(raw)
    if resolve_local_markdown_path(cleaned, source) != old_path.resolve():
        return None
    path_query, fragment_sep, fragment = cleaned.partition("#")
    _path, query_sep, query = path_query.partition("?")
    relative = Path(os.path.relpath(str(new_path), start=str(source.parent)))
    replacement = encode_link_path(relative)
    if query_sep:
        replacement += "?" + query
    if fragment_sep:
        replacement += "#" + fragment
    stripped = raw.strip()
    left = len(raw) - len(raw.lstrip())
    right = len(raw.rstrip())
    if stripped.startswith("<") and ">" in stripped:
        suffix = stripped[stripped.index(">") + 1:]
        replacement = f"<{replacement}>{suffix}"
        return raw[:left] + replacement + raw[right:]
    if raw.startswith(cleaned):
        return replacement + raw[len(cleaned):]
    return replacement


def rename_unit(base: Path, old_id: str, new_id: str, chapters: list[str]) -> dict[str, Any]:
    units = _manifest(base, chapters)
    index = next((i for i, unit in enumerate(units) if unit.id == old_id), None)
    if index is None:
        raise UnitsError(f"未知单元：{old_id}")
    if any(unit.id == new_id for unit in units):
        raise UnitsError(f"单元 ID 已存在：{new_id}")
    old = units[index]
    refs = _unit_refs(base, old_id, units, project_root=base.parent)
    if refs["external_markdown_references"]:
        raise UnitsError(
            "重命名会使工作区外的 Markdown 链接失效；请先更新这些只读资料中的链接："
            + "、".join(refs["external_markdown_references"])
        )
    new = Unit(id=new_id, chapter=old.chapter, role=old.role)
    proposed = list(units)
    proposed[index] = new
    errors = validate_units(proposed, chapters)
    if errors:
        raise UnitsError("重命名会使单元清单无效：" + "；".join(errors))

    old_paths = unit_paths(base, old_id)
    new_paths = unit_paths(base, new_id)
    _unit_artifacts(base, old_id)
    rename_map = {
        old_paths.report: new_paths.report,
        old_paths.spec: new_paths.spec,
        old_paths.page: new_paths.page,
        old_paths.preview: new_paths.preview,
        old_paths.state: new_paths.state,
        old_paths.report.with_name(f"{old_id}.{UNIT_DEPS_FILENAME}"): new_paths.report.with_name(f"{new_id}.{UNIT_DEPS_FILENAME}"),
    }
    for target in rename_map.values():
        _ensure_within_workspace(base, target)
        if target.exists() or target.is_symlink():
            raise UnitsError(f"重命名目标已存在，不会覆盖：{target.relative_to(base)}")

    rewrites: dict[Path, bytes] = {}
    for path in base.rglob("*.md"):
        relative = path.relative_to(base)
        if TRASH_DIR in relative.parents or ".state" in relative.parts or relative.as_posix() == "reports/report.md":
            continue
        if path.is_symlink():
            continue
        try:
            path.resolve().relative_to(base.resolve())
        except ValueError:
            continue
        try:
            before = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        after = before
        if path == old_paths.spec:
            after = _rewrite_identity_text(after, old_id, new_id, kind="spec")
        elif path == old_paths.report:
            after = _rewrite_identity_text(after, old_id, new_id, kind="report")
        for old_path, new_path in ((old_paths.report, new_paths.report), (old_paths.spec, new_paths.spec), (old_paths.page, new_paths.page)):
            # Mask code so examples remain byte-for-byte untouched, then replace links from right to left.
            masked = re.sub(r"```.*?```", lambda match: re.sub(r"[^\n]", " ", match.group(0)), after, flags=re.DOTALL)
            masked = re.sub(r"`[^`\n]+`", lambda match: " " * len(match.group(0)), masked)
            replacements: list[tuple[int, int, str]] = []
            target_matches = [(match, 1) for match in MARKDOWN_LINK_RE.finditer(masked)]
            for match in MARKDOWN_REF_DEF_RE.finditer(masked):
                target_group = 2 if match.group(2) is not None else 3
                target_matches.append((match, target_group))
            for match, target_group in target_matches:
                raw = after[match.start(target_group):match.end(target_group)]
                replacement = _renamed_link_target(raw, path, old_path, new_path)
                if replacement is not None:
                    replacements.append((match.start(target_group), match.end(target_group), replacement))
            for start, end, replacement in reversed(replacements):
                after = after[:start] + replacement + after[end:]
        if after != before:
            rewrites[path] = after.encode("utf-8")

    # Rename exact dependency IDs in all declarations, including other units that depend on this one.
    dep_rewrites: dict[Path, bytes] = {}
    for path in (base / "reports" / "units").glob(f"*.{UNIT_DEPS_FILENAME}"):
        if path.is_symlink():
            raise UnitsError(f"依赖声明不能是符号链接：{path.name}")
        try:
            path.resolve().relative_to(base.resolve())
        except ValueError:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UnitsError(f"依赖声明无法解析：{path.name}") from exc
        changed = False
        def update(value: Any) -> Any:
            nonlocal changed
            if isinstance(value, list):
                result = [new_id if item == old_id else update(item) for item in value]
                changed = changed or result != value
                return result
            if isinstance(value, dict):
                result = {key: update(item) for key, item in value.items()}
                return result
            return value
        updated = update(raw)
        if changed:
            dep_rewrites[path] = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    # Preserve only approvals that were current before this mechanical identity migration.
    state_backups = _snapshot_unit_states(base, units)
    approval_snapshots = {
        unit.id: refresh_unit_currency(base, unit, project_root=base.parent)
        for unit in units
    }
    changed_files: list[tuple[Path, bytes]] = []
    moved_files: list[tuple[Path, Path]] = []
    manifest_path = base / "units.json"
    manifest_backup = manifest_path.read_bytes()
    try:
        for path, content in {**rewrites, **dep_rewrites}.items():
            changed_files.append((path, path.read_bytes()))
            path.write_bytes(content)
        for source, destination in rename_map.items():
            if source.is_file():
                if source == old_paths.page:
                    changed_files.append((source, source.read_bytes()))
                    source.write_text(_rewrite_identity_text(source.read_text(encoding="utf-8"), old_id, new_id, kind="page"), encoding="utf-8")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
                moved_files.append((destination, source))
        _write_manifest_atomic(base, proposed, chapters)

        # Rebind previously current approvals to the mechanically migrated paths/IDs.
        for previous in units:
            target_id = new_id if previous.id == old_id else previous.id
            unit_now = new if target_id == new_id else previous
            current = refresh_unit_currency(base, unit_now, project_root=base.parent)
            before = approval_snapshots[previous.id]
            for kind in ("report", "spec"):
                if before[kind].get("current"):
                    if kind == "report":
                        current[kind]["approved_sha256"] = current[kind].get("content_sha256")
                        current[kind]["approved_input_fingerprint"] = current[kind].get("input_fingerprint")
                    else:
                        current[kind]["approved_sha256"] = current[kind].get("content_sha256")
                        current[kind]["report_sha256"] = current["report"].get("approved_sha256")
                        current[kind]["report_input_fingerprint"] = current["report"].get("approved_input_fingerprint")
                # Preserve audit data and make all generated HTML/check state stale.
            current["html"]["current"] = False
            current["check"]["current"] = False
            if previous.id == old_id:
                current["unit_id"] = new_id
                current.setdefault("identity_migrations", []).append({"from": old_id, "to": new_id, "at": now()})
            write_unit_state(base, target_id, current)
    except Exception:
        for destination, source in reversed(moved_files):
            source.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.replace(source)
        for path, content in reversed(changed_files):
            path.write_bytes(content)
        manifest_path.write_bytes(manifest_backup)
        for unit in proposed:
            path = unit_paths(base, unit.id).state
            if path not in state_backups:
                path.unlink(missing_ok=True)
        _restore_unit_states(state_backups)
        raise
    _invalidate_deck_checks(base, proposed)
    return {
        "renamed": True,
        "from": old.to_dict(),
        "to": new.to_dict(),
        "rewritten_markdown": [path.relative_to(base).as_posix() for path in rewrites],
        "rewritten_dependencies": [path.relative_to(base).as_posix() for path in dep_rewrites],
        "report_approval_preserved": bool(approval_snapshots[old_id]["report"].get("current")),
        "spec_approval_preserved": bool(approval_snapshots[old_id]["spec"].get("current")),
        "deck_requires_rebuild": True,
    }
