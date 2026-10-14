"""Visual evidence and an explicit agent review, separate from automated browser checks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .browser import QA_RULES_VERSION
from .dependencies import fingerprint_file
from .units import unit_paths


def _evidence(base: Path) -> tuple[Path | None, dict[str, Any]]:
    deck = base / "slides" / "index.html"
    if not deck.is_file():
        return None, {}
    directory = base / ".state" / "visual" / fingerprint_file(deck)[:16]
    manifest = directory / "measurements.json"
    try:
        return directory, json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return directory, {}


def visual_status(base: Path, unit_id: str, *, html_current: bool = True) -> dict[str, Any]:
    directory, manifest = _evidence(base)
    evidence = manifest.get("evidence") or {}
    current = bool(
        directory and html_current
        and evidence.get("deck_sha256") == fingerprint_file(base / "slides" / "index.html")
        and evidence.get("spec_sha256", {}).get(unit_id) == fingerprint_file(unit_paths(base, unit_id).spec)
        and evidence.get("rules_version") == QA_RULES_VERSION
        and any(item.get("unit_id") == unit_id for item in evidence.get("screenshots", []))
    )
    if current:
        current = all(
            (directory / item["file"]).is_file()
            and hashlib.sha256((directory / item["file"]).read_bytes()).hexdigest() == item["sha256"]
            for item in evidence["screenshots"] if item.get("unit_id") == unit_id
        )
    review_path = directory / f"review-{unit_id}.json" if directory else None
    try:
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path else {}
    except (OSError, ValueError):
        review = {}
    reviewed = bool(current and review.get("deck_sha256") == evidence.get("deck_sha256")
                    and review.get("spec_sha256") == evidence.get("spec_sha256", {}).get(unit_id)
                    and review.get("rules_version") == QA_RULES_VERSION
                    and all((directory / name).is_file() for name in review.get("images", [])))
    return {"evidence_current": current, "agent_review_current": reviewed,
            "evidence_directory": str(directory) if current else None,
            "review": review if reviewed else None}


def record_visual_review(base: Path, unit_id: str, images: list[str], notes: str) -> dict[str, Any]:
    from .state import refresh_unit_currency
    from .units import load_units_manifest

    units, errors = load_units_manifest(base, chapters=None)
    if errors or unit_id not in {unit.id for unit in units}:
        raise ValueError(f"未知单元：{unit_id}")
    unit = next(unit for unit in units if unit.id == unit_id)
    state = refresh_unit_currency(base, unit, project_root=base.parent)
    status = visual_status(base, unit_id, html_current=state["html"]["current"])
    if not status["evidence_current"] or not state["check"]["current"]:
        raise ValueError("当前单元没有有效的截图和自动浏览器检查；先运行 slides check --browser --screenshots")
    directory, manifest = _evidence(base)
    allowed = {item["file"] for item in manifest["evidence"]["screenshots"] if item["unit_id"] == unit_id}
    allowed.update(manifest["evidence"]["contacts"])
    if not images or any(name not in allowed or not (directory / name).is_file() for name in images):
        raise ValueError("--images 必须列出当前证据目录中实际审阅的截图或 contact sheet")
    if not notes.strip():
        raise ValueError("--notes 需要记录观察、修复和未解决项；不能留空")
    review = {"unit_id": unit_id, "images": images, "notes": notes.strip(),
              "at": datetime.now(timezone.utc).isoformat(),
              "deck_sha256": manifest["evidence"]["deck_sha256"],
              "spec_sha256": manifest["evidence"]["spec_sha256"][unit_id],
              "rules_version": QA_RULES_VERSION, "reviewer": "agent"}
    target = directory / f"review-{unit_id}.json"
    target.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"review": str(target), "status": "agent-reviewed", "user_approved": False}
