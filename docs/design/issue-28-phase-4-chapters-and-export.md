# Issue 28 — Phase 4: Chapter sync and delivery design

Status: design confirmed; Phase 4 implementation is in progress.

## Scope

This phase adds two top-level capabilities that round out the v2 workflow:

- `my-slides chapters list/add/rename/remove/move` to keep `project.yaml`,
  `units.json`, and `wiki/index.md` aligned after structural decisions.
- `my-slides export [--output DIR]` to deliver the assembled deck as
  `<project>-v<N>-<date>.html` and record deliveries in `.state/deliveries.json`.

## Chapter operations

### Data model

A chapter is the canonical key that ties together three stores:

| Store | Field | Notes |
| --- | --- | --- |
| `project.yaml` | `chapters: [...]` | Ordered list; canonical order. |
| `units.json` | `units[].chapter` | Per-unit reference; must come from the same string set as the YAML list. |
| `wiki/index.md` | `## <chapter>` | One heading per chapter; `## 补充研究` stays at the end. |

### Behaviour summary

| Command | project.yaml | units.json | wiki/index.md | Approvals |
| --- | --- | --- | --- | --- |
| `chapters list` | reads | reads | reads | read-only |
| `chapters add <name> [--after CHAPTER]` | appends or inserts | unchanged | inserts heading | read-only |
| `chapters rename <old> <new>` | replaces | rewrites every affected `chapter` field | replaces heading | unchanged (content hashes / dependency fingerprints stay identical) |
| `chapters remove <name>` | removes the entry | unchanged when no units reference it; refuses otherwise | drops the heading | read-only |
| `chapters move <name> [--after \| --before CHAPTER]` | reorders | writes the manifest again so order matches the YAML; refuses on invalid order | reorders the heading blocks | unchanged (order does not bind approvals) |

`chapters rename` preserves approvals because the content hash and the
report input fingerprint (closure of local file deps) do not depend on the
chapter string. `refresh_unit_currency` keeps `report.current` and
`spec.current` True after a rename, so the user does not need to
re-approve. The CLI prints an explicit note explaining why and reminds the
user to rebuild the full deck.

`chapters remove` is refused when any unit still references the chapter;
the error message lists the offending unit IDs so the agent can move
them first. The cover unit, if assigned to the chapter, is listed too.

### Edge cases

- Duplicate chapter names: `add` refuses; `rename` to an existing name refuses.
- Renaming the only remaining chapter: refused to keep at least one theme.
- Removing the only remaining chapter: refused.
- Wiki index missing: heading edits are skipped silently; YAML/units
  changes still happen so the agent can recover later.

## Export and deliveries

### Output naming

`<safe_project_name>-v<N>-<YYYY-MM-DD>.html`. The `<N>` resets per day
so two deliveries on the same day get `-v1-`, `-v2-`, …; deliveries on
later days start again at `-v1-`. The safe project name strips
characters that are unsafe in filenames (`\ / : * ? " < > |`) and trims
whitespace.

### Pre-flight checks

Refuses the export when any unit is not current. The check covers the
same fields that `status --json` already exposes:

- `state["report"]["current"]` — approved content hash and dependency
  fingerprint match the on-disk files.
- `state["spec"]["current"]` — Spec hash and bound report hash match.
- `state["html"]["current"]` — built page matches the bound Spec.
- `state["check"]["current"]` — browser check result bound to the
  measured deck is still valid.

The error message lists every blocker (unit id + which layer failed)
so the agent can fix them before re-running. `--no-check` is intentionally
not provided: delivery without a current browser check is a real risk and
the user opted into it by running the export.

### Delivery record

Each successful export appends one entry to `.state/deliveries.json`:

```json
{
  "format_version": "v2",
  "package_version": "0.4.3",
  "deliveries": [
    {
      "sequence": 1,
      "date": "2026-10-13",
      "delivered_at": "2026-10-13T12:34:56+08:00",
      "project": "Demo",
      "file": "Demo-v1-2026-10-13.html",
      "path": "/abs/path/to/Demo-v1-2026-10-13.html",
      "deck_sha256": "…",
      "units": [
        {
          "id": "cover",
          "chapter": "投资概要",
          "title": "",
          "report_sha256": "…",
          "spec_sha256": "…",
          "html_sha256": "…",
          "report_approved_by": "Reviewer",
          "spec_approved_by": "Reviewer"
        }
      ]
    }
  ]
}
```

The package version is recorded so an offline delivery record can be
matched against the tool that produced it.

### `status --json` additions

A new top-level `delivery` key:

```json
"delivery": {
  "has_delivery": true,
  "last_delivery": { … same shape as one entry above … },
  "changed_since": [
    {"unit": "alpha", "reason": "报告正文、Spec 已变化"}
  ],
  "unchanged_since": ["cover"],
  "deck_changed": false
}
```

`deck_changed` compares the on-disk `slides/index.html` SHA-256 with the
deck SHA-256 in the last delivery; a difference means someone edited the
deck outside the tool or replaced the formal file.

When no delivery has been made yet, `delivery` is `{"has_delivery": false}`.

## Worked example

1. The agent finishes a first deck; `my-slides export` writes
   `Demo-v1-2026-10-13.html` and the first delivery record.
2. The user notices a chapter title typo in `wiki/index.md`.
3. The agent runs `my-slides chapters rename "公司概况" "公司介绍"`.
   `project.yaml` updates, the single `chapter-02-01` unit's `chapter`
   field updates, and the Wiki heading is rewritten. The report and Spec
   approvals stay bound.
4. The agent rebuilds the deck with `my-slides slides build --all` (HTML
   is stale because the deck needs the new chapter order).
5. The agent re-runs `my-slides export`. A new file `Demo-v2-2026-10-13.html`
   lands in the output directory and `.state/deliveries.json` now has two
   entries.
6. `my-slides status --json` lists the last delivery (sequence 2,
   `2026-10-13`) and the units changed since the last delivery.

## Open follow-ups (not in this phase)

- `clean` for `.state/snapshots/wiki/` and `work/` handoffs.
- `next --all` to dump the full backlog in one shot.
- Distinguishing `slides check` structural and browser roles in `agent help`.
