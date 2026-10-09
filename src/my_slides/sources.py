"""Markdown source discovery and ingestion state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project import app_path, now

EXCLUDED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__"}
EXCLUDED_FILES = {"agents.md", "claude.md", "gemini.md", "copilot-instructions.md"}


def discover_sources(root: Path, cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    app = app_path(root).resolve()
    found: dict[str, dict[str, Any]] = {}
    for entry in cfg.get("source_dirs", ["."]):
        candidate = (root / entry).resolve()
        if not candidate.is_dir():
            continue
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        for path in candidate.rglob("*.md"):
            if app in path.parents or path.name.lower() in EXCLUDED_FILES:
                continue
            if any(part.lower() in EXCLUDED_DIRS or part.startswith(".") for part in path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            found[rel] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    return found


def scan_sources(root: Path, base: Path, cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    state_path = base / ".state" / "sources.json"
    old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"files": {}}
    current = discover_sources(root, cfg)
    previous = old.get("files", {})
    pending: list[str] = []
    removed: list[str] = []
    merged: dict[str, Any] = {}
    for name, value in current.items():
        prior = previous.get(name, {})
        ingested = prior.get("ingested_sha256")
        merged[name] = {**value, "ingested_sha256": ingested}
        if ingested != value["sha256"]:
            pending.append(name)
    for name, prior in previous.items():
        if name not in current:
            merged[name] = {**prior, "removed": True}
            if not prior.get("removed_acknowledged_at"):
                removed.append(name)
    state = {"scanned_at": now(), "files": merged}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state, sorted(pending), sorted(removed)


def mark_ingested(base: Path, names: list[str] | None = None) -> int:
    path = base / ".state" / "sources.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"files": {}}
    selected = set(names or state["files"].keys())
    count = 0
    for name, item in state["files"].items():
        if name in selected and item.get("removed") and not item.get("removed_acknowledged_at"):
            item["removed_acknowledged_at"] = now()
            count += 1
        elif name in selected and not item.get("removed"):
            item["ingested_sha256"] = item["sha256"]
            count += 1
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count
