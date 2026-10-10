---
name: my-slides-workflow
description: Use the local my-slides CLI to maintain an investment project's Markdown Wiki, prepare and validate an investment report and Presentation Spec, and build offline HTML slides.
---

# My Slides investment workflow

Use this skill when working inside an investment project that contains `my-slides/project.yaml`.

Projects use `units.json` and unit directories (created by `my-slides init`). Run `my-slides units list`, `my-slides status --json`, and `my-slides next --json` first. `next` returns a command, target unit, reason, and `actor`. Use `--unit <id>` (or `--changed` / `--all`) with `prepare` / `validate` / `approve` / `slides build` / `slides check`. Assemble the full report with `my-slides assemble` after unit report confirmations.

Projects without `units.json` need `my-slides init` before other commands.

`slides check` without `--browser` is structural only (unit set/order, cover). Add `--browser` after `my-slides browser install` for viewport QA.

`prepare` updates fixed files in `my-slides/work/` (`wiki.md`, `wiki-question.md`, or `<kind>/<unit-id>.md`). Reuse the returned path; repeated preparation does not create new timestamped handoffs.

## Repository version bump (when changing this package)

If your PR merges code or docs into the **my-slides** repo `main`: bump `pyproject.toml` `[project].version` patch by +1 in that same PR before merge. `my-slides --version` must match. Do not rely on CI. Full rule: repo-root `AGENTS.md`.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the configured report chapter themes and their order (Wiki index / `project.yaml` chapters). Delivery structure comes from `units.json`.
- Use `my-slides units add/move/rename/remove` for inventory changes; never edit `units.json` manually. `units move` accepts `--after` or `--before`; omit both to append to the target chapter, including a chapter that currently has no units. A chapter-only move requires report reconfirmation, while an unchanged report keeps its Spec approval. Same-chapter order changes and renames require rebuilding the full deck and rerunning checks.
- `my-slides units remove <id>` is a read-only impact preview. Review its files, approvals, dependencies, and Markdown references before using `--yes`. Removal is recoverable, so an Agent may run `--yes`, but if the preview shows any prior report or Spec approval, first ask the user for explicit consent. Never remove a blocked unit. Include the printed `my-slides units restore <trash-id>` command in the result; use `units trash list` to find other recoverable entries. Trash is not part of source scans or delivery.
- State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- `approve report/spec` only submits a pending review request. Never run `confirm` for the user, even when `next --json` shows its command; stop and ask the user to review the specified file and run it in their own terminal. `actor: human` is a hard handoff point for the Agent. Never run `confirm` through a pseudo-terminal or input automation (`script`, `expect`, tmux `send-keys`, piping answers), and never read `.state/` to construct its confirmation phrase.
- Generate HTML only from approved Specs. Write one content fragment per unit using the component examples from `prepare slides`. Keep custom styles scoped; include one `slide-notes` JSON block on every slide. Use only approved `echarts-spec` and Lucide markers. Do not use a CDN. The editorial-light shell, fonts, and navigation are added by `slides build` into `slides/previews/<id>.html` and `slides/index.html`.

## Workflow

1. `my-slides status` and `my-slides sources scan`. Update Wiki, then `validate wiki` and `sources mark-ingested`.
2. `prepare report --unit <id>` → write `reports/units/<id>.md` → `validate report --unit <id>` → `approve report --unit <id>` to request review → user reviews and personally runs `confirm report --unit <id>` → `assemble`.
3. `prepare spec --unit <id>` → write one-page Spec in `specs/units/<id>.md` (page ID = unit ID) → validate → `approve spec --unit <id>` to request review → user reviews and personally runs `confirm spec --unit <id>`.
4. `prepare slides --unit <id>` → write `slides/pages/<id>.html` → `slides build --unit <id>` → `slides check --unit <id>` (structural); optionally `slides check --unit <id> --browser`.

## Useful commands

```text
my-slides status
my-slides next --json
my-slides sources scan
my-slides prepare wiki [--question "..."]
my-slides validate wiki
my-slides sources mark-ingested
my-slides units list
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>
my-slides confirm report --unit <id>  # user executes, never Agent
my-slides assemble
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides confirm spec --unit <id>    # user executes, never Agent
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id>
my-slides slides check --unit <id> --browser
```

Use `--project <path>` when the agent's current directory is outside the project.
