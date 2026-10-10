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

For a PR into the **my-slides** repo `main`, select a version step that matches impact, add a matching `CHANGELOG.md` entry, and let PR CI validate both. Compatible additions, fixes, and docs use patch +1; incompatible changes on 0.x use minor +1 and reset patch to 0, with a Breaking Changes section in the changelog. A major bump requires the maintainer's `version:major` PR label. PRs that only change `.github/`, `tests/`, or `scripts/` may skip the bump. Development `--version` output includes the short commit and dirty state; installed packages without Git metadata show only the version. After tests pass on `main`, CI creates and pushes the annotated `vX.Y.Z` tag. See repo-root `AGENTS.md` and `docs/versioning.md`.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the configured report chapter themes and their order (Wiki index / `project.yaml` chapters). Delivery structure comes from `units.json`.
- Use `my-slides units add/move/rename/remove` for inventory changes; never edit `units.json` manually. `units move` accepts `--after` or `--before`; omit both to append to the target chapter, including a chapter that currently has no units. A chapter-only move requires report reconfirmation, while an unchanged report keeps its Spec approval. Same-chapter order changes and renames require rebuilding the full deck and rerunning checks.
- `my-slides units remove <id>` is a read-only impact preview. Review its files, approvals, dependencies, and Markdown references before using `--yes`. Removal is recoverable, so an Agent may run `--yes`, but if the preview shows any prior report or Spec approval, first ask the user for explicit consent. Never remove a blocked unit. Include the printed `my-slides units restore <trash-id>` command in the result; use `units trash list` to find other recoverable entries. Trash is not part of source scans or delivery.
- State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- `approve report/spec` only submits a pending review request. When `next` returns `actor: human`, run the suggested `review` command, paste its output into the conversation, and stop. On the user's next message, run `confirm --via chat` only if that message explicitly approves the named section or chapter. Pass that message unchanged as `--user-reply`. Do not treat "continue", "looks fine", or "next" as approval, and do not widen the scope. Never invent a phrase: copy it from the latest `review`. Never run `confirm` through a pseudo-terminal or input automation (`script`, `expect`, tmux `send-keys`, piping answers). If `project.yaml` sets `approval_mode: terminal`, do not run `confirm` at all; ask the user to run it in their own terminal.
- After the Wiki is ready, propose a 大章节 → 小章节 outline in the conversation (for example 行业分析 / 需求分析, 竞争分析). Create each section with `units add <id> --chapter <大章节> --title <小章节名>` only after the user accepts the outline. `units retitle` changes the display name and keeps existing approvals.
- Generate HTML only from approved Specs. One unit is one section and may contain multiple slides: the HTML page count must equal the Spec's `## Slide N` count (cover is one page; a content section has at most 8). Keep custom styles scoped; include one `slide-notes` JSON block on every slide. A slide may use only the `echarts-spec` and Lucide icons declared on that same Spec page. Do not use a CDN. The editorial-light shell, fonts, and navigation are added by `slides build` into `slides/previews/<id>.html` and `slides/index.html`. Changing only slide layout does not require a new approval; changing Spec content requires re-approval of that section only.

## Workflow

1. `my-slides status` and `my-slides sources scan`. Update Wiki, then `validate wiki` and `sources mark-ingested`.
2. `prepare report --unit <id>` → write `reports/units/<id>.md` → `validate report --unit <id>` → `approve report --unit <id>` (or `--chapter`) → `review report` → paste it and wait → after an explicit user approval, `confirm report --via chat` → `assemble`.
3. `prepare spec --unit <id>` → write the section Spec in `specs/units/<id>.md` (one `## Slide N —` block per page; `单元 ID` equals the unit ID; a legacy `页面 ID` line is still accepted) → validate → `approve spec` → `review spec` → paste it and wait → after an explicit user approval, `confirm spec --via chat`.
4. `prepare slides --unit <id>` → write `slides/pages/<id>.html` with one `<section class="slide">` per Spec page → `slides build --unit <id>` → `slides check --unit <id>` (structural); optionally `slides check --unit <id> --browser`.

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
my-slides approve report --chapter <大章节>
my-slides review report --unit <id>
my-slides confirm report --unit <id> --via chat --phrase "APPROVE REPORT <id> <sha12>" --user-reply "<用户原话>"
my-slides assemble
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides review spec --chapter <大章节>
my-slides confirm spec --chapter <大章节> --via chat --phrase "APPROVE SPEC <大章节> <sha12>" --user-reply "<用户原话>"
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id>
my-slides slides check --unit <id> --browser
```

Use `--project <path>` when the agent's current directory is outside the project.
