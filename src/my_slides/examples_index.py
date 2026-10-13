"""Index the bundled example library and surface matches for Spec handoffs.

The example library lives under ``skills/my-slides-workflow/example/`` in the
repository and under ``src/my_slides/templates/examples/`` in the packaged
wheel. ``scripts/sync-skill-templates.py`` keeps the two copies in step. This
module reads the bundled ``examples/index/problems.yaml`` and matches the
current Spec against the entries' ``signals`` (keywords) and ``relation``
labels, then returns the 1–2 most relevant examples as ``path`` + ``summary``
pairs.

The handoff only surfaces paths and one-line summaries; the full example
content stays out of the agent's context window.

The index is intentionally parsed with a small stdlib-only parser to avoid
adding a runtime dependency on PyYAML. The expected format is constrained
(see ``skills/my-slides-workflow/example/index/problems.yaml``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

INDEX_FILE = "examples/index/problems.yaml"
RELATION_RE = re.compile(
    r"^####\s+关系类型\s*\n(?P<body>.*?)(?=^####\s|\Z)", re.MULTILINE | re.DOTALL
)
LAYOUT_INTENT_RE = re.compile(
    r"^###\s+布局意图\s*\n(?P<body>.*?)(?=^###\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class ExampleMatch:
    id: str
    path: str
    title: str
    summary: str
    score: int
    matched_signals: tuple[str, ...] = field(default_factory=tuple)
    matched_relation: str | None = None


def _read_index_text() -> str:
    """Return the YAML index text from the packaged templates."""
    resource = files("my_slides").joinpath("templates", INDEX_FILE)
    if not resource.is_file():
        raise FileNotFoundError(f"examples index missing: {INDEX_FILE}")
    return resource.read_text(encoding="utf-8")


def load_examples_index() -> list[dict[str, Any]]:
    """Parse the bundled ``problems.yaml`` index into a list of entries.

    Supports the constrained subset of YAML used by ``problems.yaml``:

    * top-level list of ``-`` entries;
    * scalar ``key: value`` mappings (single line);
    * nested list-of-strings (``key:\\n  - value``);
    * ``#`` comments and blank lines.
    """
    text = _read_index_text()
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_key: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        leading = len(line) - len(line.lstrip())
        stripped = line.lstrip()
        # Top-level (no indent) ``- entry`` lines start a new record.
        if leading == 0 and stripped.startswith("- "):
            if current is not None:
                entries.append(current)
            current = {}
            list_key = None
            inline = stripped[2:]
            if ":" in inline:
                key, _, value = inline.partition(":")
                key = key.strip()
                value = value.strip()
                current[key] = value
                list_key = key if value == "" else None
            continue
        if current is None:
            continue
        # Nested ``- item`` belongs to the most recent list key.
        if stripped.startswith("- "):
            target = current.get(list_key) if list_key else None
            if isinstance(target, list):
                target.append(stripped[2:].strip())
            continue
        # ``key:`` / ``key: value`` mappings.
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "" or value == "[]":
                current[key] = []
                list_key = key
            else:
                current[key] = value
                list_key = None
            continue
    if current is not None:
        entries.append(current)
    return entries


def _extract_spec_signal_text(spec_text: str) -> tuple[str, str | None]:
    """Return the 布局意图 body and the first line of the 关系类型 sub-point."""
    intent_match = LAYOUT_INTENT_RE.search(spec_text)
    intent_body = intent_match.group("body") if intent_match else ""
    relation: str | None = None
    relation_match = RELATION_RE.search(intent_body)
    if relation_match:
        body = relation_match.group("body").strip()
        if body:
            relation = body.splitlines()[0].strip()
    return intent_body, relation


def _score_entry(
    entry: dict[str, Any],
    spec_text: str,
    intent_body: str,
    declared_relation: str | None,
) -> ExampleMatch | None:
    signals: list[str] = list(entry.get("signals") or [])
    entry_relation = str(entry.get("relation") or "").strip()
    score = 0
    matched_signals: list[str] = []
    haystack = (spec_text + "\n" + intent_body).lower()
    for signal in signals:
        if signal and signal.lower() in haystack:
            score += 3
            matched_signals.append(signal)
    if declared_relation and entry_relation:
        normalized_decl = re.sub(r"\s+", "", declared_relation)
        normalized_entry = re.sub(r"\s+", "", entry_relation)
        if normalized_decl == normalized_entry:
            score += 4
        elif (
            normalized_decl
            and normalized_entry
            and (
                normalized_decl in normalized_entry
                or normalized_entry in normalized_decl
            )
        ):
            score += 2
    if score <= 0 and not matched_signals:
        return None
    return ExampleMatch(
        id=str(entry.get("id") or ""),
        path=str(entry.get("path") or ""),
        title=str(entry.get("title") or ""),
        summary=str(entry.get("summary") or ""),
        score=score,
        matched_signals=tuple(matched_signals),
        matched_relation=entry_relation if declared_relation else None,
    )


def select_examples(
    spec_text: str,
    *,
    limit: int = 2,
    index: list[dict[str, Any]] | None = None,
) -> list[ExampleMatch]:
    """Return the top ``limit`` examples that best match the given Spec text."""
    intent_body, declared_relation = _extract_spec_signal_text(spec_text)
    if index is None:
        index = load_examples_index()
    candidates: list[ExampleMatch] = []
    for entry in index:
        match = _score_entry(entry, spec_text, intent_body, declared_relation)
        if match is not None:
            candidates.append(match)
    candidates.sort(key=lambda item: (-item.score, item.id))
    if not candidates:
        # Fallback: pick the entry with the empty ``signals`` list (default).
        for entry in index:
            if not list(entry.get("signals") or []):
                candidates.append(
                    ExampleMatch(
                        id=str(entry.get("id") or ""),
                        path=str(entry.get("path") or ""),
                        title=str(entry.get("title") or ""),
                        summary=str(entry.get("summary") or ""),
                        score=0,
                    )
                )
                break
    # Deduplicate by ``path`` (the default fallback entry may reuse a path
    # that already won a higher score).
    seen: set[str] = set()
    unique: list[ExampleMatch] = []
    for match in candidates:
        if match.path in seen:
            continue
        seen.add(match.path)
        unique.append(match)
        if len(unique) >= limit:
            break
    if len(unique) < limit:
        for match in candidates:
            if match.path in seen:
                continue
            seen.add(match.path)
            unique.append(match)
            if len(unique) >= limit:
                break
    return unique[:limit]


def format_matches(matches: Iterable[ExampleMatch]) -> str:
    """Render matches as a short Markdown list for the handoff."""
    blocks: list[str] = []
    for match in matches:
        if not match.path:
            continue
        blocks.append(f"- `{match.path}` — {match.title}：{match.summary}")
    return "\n".join(blocks)


def read_unit_spec_text(spec_path: Path) -> str:
    """Read the Spec markdown for matching (returns empty string if missing)."""
    if not spec_path.is_file():
        return ""
    return spec_path.read_text(encoding="utf-8")
