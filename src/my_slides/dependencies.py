"""Local Markdown / unit dependency discovery for v2 projects.

Product rule (P3-8): in v2, report approval stays valid when a Wiki page changes
only if that unit's report (and its recursive local deps) do not reference the
changed page. Changing a linked Wiki invalidates the units that actually depend
on it — never a global source_digest wipe.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .units import (
    Unit,
    UnitsError,
    iter_local_markdown_targets,
    resolve_local_markdown_path,
    unit_paths,
)

# Explicit unit→unit edges stored beside the unit report (optional sidecar).
UNIT_DEPS_FILENAME = "depends-on.json"


def content_fingerprint(data: bytes | str) -> str:
    """SHA-256 of LF-normalized text, or raw bytes when the payload is not UTF-8.

    图片等二进制不能按文本解码；解码失败时直接哈希原始字节，换行规范化只用于文本。
    """
    import hashlib

    if isinstance(data, str):
        payload = data.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            payload = data
        else:
            payload = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fingerprint_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return content_fingerprint(path.read_bytes())


def fingerprint_json(value: Any) -> str:
    """Deterministic JSON fingerprint (sorted keys, compact separators)."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return content_fingerprint(payload)


def local_file_dependencies(path: Path, *, root: Path | None = None) -> list[Path]:
    """Collect local files linked from path (non-recursive)."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    found: list[Path] = []
    seen: set[Path] = set()
    for target in iter_local_markdown_targets(text):
        resolved = resolve_local_markdown_path(target, path)
        if resolved is None or not resolved.exists():
            continue
        resolved = resolved.resolve()
        if root is not None:
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                continue
        if resolved not in seen:
            seen.add(resolved)
            found.append(resolved)
    return found


def walk_local_dependencies(
    start: Path,
    *,
    root: Path | None = None,
    max_nodes: int = 500,
) -> tuple[list[Path], list[str]]:
    """BFS over local Markdown links with cycle-safe visited set.

    Returns (files in discovery order excluding start, cycle warnings).
    """
    start = start.resolve()
    warnings: list[str] = []
    ordered: list[Path] = []
    visited: set[Path] = {start}
    stack_path: dict[Path, list[Path]] = {start: [start]}
    queue: deque[Path] = deque([start])
    while queue:
        current = queue.popleft()
        if len(visited) > max_nodes:
            warnings.append(f"依赖遍历超过 {max_nodes} 个文件，已截断")
            break
        for child in local_file_dependencies(current, root=root):
            if child in stack_path[current]:
                cycle = stack_path[current] + [child]
                warnings.append(
                    "检测到本地链接环："
                    + " → ".join(_display(p, root) for p in cycle)
                    + "（已跳过重复节点，请打断环后再审阅）"
                )
                continue
            if child in visited:
                continue
            visited.add(child)
            ordered.append(child)
            stack_path[child] = stack_path[current] + [child]
            if child.suffix.lower() in {".md", ".markdown"}:
                queue.append(child)
    return ordered, warnings


def _display(path: Path, root: Path | None) -> str:
    if root is None:
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_explicit_unit_deps(base: Path, unit_id: str) -> list[str]:
    """Optional reports/units/<id>.depends-on.json listing other unit ids."""
    path = unit_paths(base, unit_id).report.with_name(f"{unit_id}.{UNIT_DEPS_FILENAME}")
    # Prefer sidecar next to the unit report: <id>.depends-on.json
    sidecar = unit_paths(base, unit_id).report.parent / f"{unit_id}.{UNIT_DEPS_FILENAME}"
    if not sidecar.is_file():
        return []
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnitsError(f"{sidecar.name} JSON 无效：{exc}") from exc
    if isinstance(data, dict):
        data = data.get("depends_on", data.get("units", []))
    if not isinstance(data, list) or any(not isinstance(item, str) for item in data):
        raise UnitsError(f"{sidecar.name} 必须是单元 ID 字符串数组（或含 depends_on 字段）")
    return [item for item in data if item]


def build_unit_dependency_graph(base: Path, units: list[Unit]) -> dict[str, list[str]]:
    """Map unit id → explicit depends_on unit ids (edges toward dependencies)."""
    known = {unit.id for unit in units}
    graph: dict[str, list[str]] = {unit.id: [] for unit in units}
    for unit in units:
        deps = load_explicit_unit_deps(base, unit.id)
        unknown = [dep for dep in deps if dep not in known]
        if unknown:
            raise UnitsError(f"单元 {unit.id} 声明了未知依赖：{'、'.join(unknown)}")
        if unit.id in deps:
            raise UnitsError(f"单元 {unit.id} 不能依赖自身")
        graph[unit.id] = list(dict.fromkeys(deps))
    return graph


def detect_unit_cycles(graph: dict[str, list[str]]) -> list[str]:
    """Return Chinese error strings describing each cycle found (empty if DAG)."""
    errors: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        visiting.add(node)
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt in visiting:
                idx = stack.index(nxt)
                cycle = stack[idx:] + [nxt]
                errors.append(
                    "单元依赖成环："
                    + " → ".join(cycle)
                    + "。请从 depends-on.json 中去掉至少一条边以打断环。"
                )
            elif nxt not in visited:
                dfs(nxt)
        stack.pop()
        visiting.discard(node)
        visited.add(node)

    for node in graph:
        if node not in visited:
            dfs(node)
    # Deduplicate identical cycle messages.
    return list(dict.fromkeys(errors))


def unit_dependency_version(
    base: Path,
    unit_id: str,
    *,
    project_root: Path | None = None,
    stack: set[str] | None = None,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fingerprint one unit's report, local files, and recursive upstream versions.

    只记录上游 ID 不够：上游正文或它自己的引用变化时，下游批准也必须失效。
    """
    stack = set() if stack is None else stack
    cache = {} if cache is None else cache
    if unit_id in cache and unit_id not in stack:
        return cache[unit_id]
    if unit_id in stack:
        return {"unit_id": unit_id, "cycle": True}
    stack.add(unit_id)
    report = unit_paths(base, unit_id).report
    root = project_root or base.parent
    deps, _warnings = walk_local_dependencies(report, root=root) if report.is_file() else ([], [])
    file_fps: dict[str, str] = {}
    for path in deps:
        digest = fingerprint_file(path)
        if digest is not None:
            file_fps[_display(path, root)] = digest
    nested = {
        dep_id: unit_dependency_version(
            base,
            dep_id,
            project_root=project_root,
            stack=stack,
            cache=cache,
        )
        for dep_id in load_explicit_unit_deps(base, unit_id)
    }
    stack.remove(unit_id)
    version = {
        "report_sha256": fingerprint_file(report),
        "local_files": file_fps,
        "depends_on_units": nested,
    }
    cache[unit_id] = version
    return version


def report_closure_fingerprints(
    base: Path,
    unit: Unit,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Fingerprints for a unit report + recursive local file deps (+ upstream versions)."""
    report = unit_paths(base, unit.id).report
    root = project_root or base.parent
    _deps, warnings = walk_local_dependencies(report, root=root) if report.is_file() else ([], [])
    version = unit_dependency_version(base, unit.id, project_root=project_root)
    return {
        "unit_id": unit.id,
        "report_sha256": version["report_sha256"],
        "local_files": version["local_files"],
        "depends_on_units": version["depends_on_units"],
        "warnings": warnings,
    }


def units_affected_by_file(
    base: Path,
    units: list[Unit],
    changed: Path,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Return units whose report closure includes ``changed``."""
    changed = changed.resolve()
    root = project_root or base.parent
    affected: list[str] = []
    reasons: dict[str, str] = {}
    paths_by_unit: dict[str, list[str]] = {}
    for unit in units:
        report = unit_paths(base, unit.id).report
        if not report.is_file():
            continue
        if report.resolve() == changed:
            affected.append(unit.id)
            reasons[unit.id] = f"报告正文变化：{_display(changed, root)}"
            paths_by_unit[unit.id] = [_display(changed, root)]
            continue
        deps, _ = walk_local_dependencies(report, root=root)
        if any(dep.resolve() == changed for dep in deps):
            affected.append(unit.id)
            chain = [_display(report, root), _display(changed, root)]
            reasons[unit.id] = "本地依赖变化：" + " → ".join(chain)
            paths_by_unit[unit.id] = chain
    # Propagate via explicit unit→unit edges (dependents of affected).
    graph = build_unit_dependency_graph(base, units)
    reverse: dict[str, list[str]] = defaultdict(list)
    for src, deps in graph.items():
        for dep in deps:
            reverse[dep].append(src)
    queue = deque(affected)
    seen = set(affected)
    while queue:
        node = queue.popleft()
        for dependent in reverse.get(node, []):
            if dependent in seen:
                continue
            seen.add(dependent)
            affected.append(dependent)
            reasons[dependent] = f"上游单元变化：{node}"
            paths_by_unit[dependent] = [node, dependent]
            queue.append(dependent)
    return {
        "changed": _display(changed, root),
        "affected_units": affected,
        "reasons": reasons,
        "paths": paths_by_unit,
    }


def reliable_relpath(path: Path, start: Path) -> Path:
    """Cross-drive-safe relative path (P3-13); wraps os.path.relpath."""
    import os

    return Path(os.path.relpath(str(path.resolve()), start=str(start.resolve())))
