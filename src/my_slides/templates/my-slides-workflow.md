---
name: my-slides-workflow
description: Use the local my-slides CLI to maintain an investment project's Markdown Wiki, write and get approval for a unit-based investment report, then author the deck in Design+Slides for the user to review and hand-edit on 127.0.0.1:5173 and export as offline HTML.
---

# My Slides investment workflow

Use this skill when working inside an investment project that contains `my-slides/project.yaml`.

Flow: sources → Wiki → unit reports (user approves each) → assembled report → evidence numbers → Design+Slides deck → user review on 5173 → offline HTML export. my-slides owns content and orchestration; Design+Slides (located through `MY_SLIDES_DESIGN_ROOT`) owns page format, the editor, and export.

Projects use `units.json` and unit directories (created by `my-slides init`). Run `my-slides units list`, `my-slides status --json`, and `my-slides next --json` first. `next` returns a command, target unit, reason, and `actor`; `actor: human` means stop and hand over to the user. Use `--unit <id>` (or `--changed` / `--all`) with `prepare` / `validate` / `approve` / `slides build` / `slides check`. Projects without `units.json` need `my-slides init` before other commands. Run `my-slides doctor` to confirm the Design engine is ready (`design.ready`) before the slides stage.

`prepare` updates fixed files in `my-slides/work/` (`wiki.md`, `wiki-question.md`, `evidence-research.md`, or `<report|slides>/<unit-id>.md`). Reuse the returned path; repeated preparation does not create new timestamped handoffs.

After report assembly and before writing pages, run `my-slides prepare evidence-research` and complete `my-slides/research/numbers.md` with sourced public figures. Run `my-slides validate evidence-research`; `next` recommends this phase when the list is missing or invalid. Use a number on the single page where it best supports the conclusion; each ID may appear at most once across the deck. A page without a relevant figure may use a table or structural diagram.

## On-demand references

This skill entry stays short. Read the references below only when the step you're about to do needs them. The packaged install mirrors this layout under `my_slides/templates/references/`.

| When you are about to … | Open |
| --- | --- |
| Read or update the project Wiki | `references/wiki.md` |
| Write a report section | `references/report.md` |
| Write or revise Design pages from an approved report | `references/slides.md`, then Design's own `<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md` for page format |
| Choose a chart type, draw it as inline SVG, or sanity-check data | `references/charts.md` |
| Pick a layout / find a reference example | `references/example-index.md` |
| Decide whether to draw a value flow, dependency, or process diagram | `references/static-diagrams.md` |
| Review layout variety and page density before handing the deck to the user | `references/visual-rules.md` |

The reference set is shared between the in-repo `skills/my-slides-workflow/` and the packaged `src/my_slides/templates/` mirror. `scripts/sync-skill-templates.py` keeps both copies in step and CI checks it. Do not hand-edit `templates/` only.

## Repository version bump (when changing this package)

For a PR into the **my-slides** repo `main`, select a version step that matches impact, add a matching `CHANGELOG.md` entry, and let PR CI validate both. Compatible additions, fixes, and docs use patch +1; incompatible changes on 0.x use minor +1 and reset patch to 0, with a Breaking Changes section in the changelog. A major bump requires the maintainer's `version:major` PR label. PRs that only change `.github/`, `tests/`, or `scripts/` may skip the bump. After tests pass on `main`, CI creates and pushes the annotated `vX.Y.Z` tag. See repo-root `AGENTS.md` and `docs/versioning.md`.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the configured report chapter themes and their order (Wiki index / `project.yaml` chapters). Delivery structure comes from `units.json`.
- After the Wiki is ready, propose a 大章节 → 小章节 outline in the conversation (for example 行业分析 / 需求分析, 竞争分析). Create each section with `units add <id> --chapter <大章节> --title <小章节名>` only after the user accepts the outline. `units retitle` changes the display name and keeps existing approvals.
- Use `my-slides units add/move/rename/remove` for inventory changes; never edit `units.json` manually. `units move` accepts `--after` or `--before`; omit both to append to the target chapter. A chapter-only move requires report reconfirmation. After any inventory change, run `slides build --all` and `slides check --all` again.
- Use `my-slides chapters list/add/rename/remove/move` to keep `project.yaml`, `units.json`, and `wiki/index.md` in sync. Renaming a chapter keeps report approvals; removing a chapter that still has units is refused.
- `my-slides units remove <id>` is a read-only impact preview. Review its files, approvals, dependencies, and Markdown references before using `--yes`. Removal moves the report and the unit's Design pages into recoverable trash, so an Agent may run `--yes`, but if the preview shows a prior report approval, first ask the user for explicit consent. Never remove a blocked unit. Include the printed `my-slides units restore <trash-id>` command in the result.
- State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- `approve report` only submits a pending review request. When `next` returns `actor: human`, run the suggested `review` command, paste its output into the conversation, and stop. On the user's next message, run `confirm --via chat` only if that message explicitly approves the named section or chapter. Pass that message unchanged as `--user-reply`. Do not treat "continue", "looks fine", or "next" as approval, and do not widen the scope. Never invent a phrase: copy it from the latest `review`. Never run `confirm` through a pseudo-terminal or input automation (`script`, `expect`, tmux `send-keys`, piping answers). If `project.yaml` sets `approval_mode: terminal`, do not run `confirm` at all; ask the user to run it in their own terminal.
- The user can also reject or revoke. `reject report --unit <id> --reason "..."` clears the pending request and records the reason; it only declines the current pending version and never invalidates an already approved report. `withdraw report --unit <id>` is for the agent to drop one of its own requests and never counts as a user decision. `revoke report --unit <id> [--reason ...]` drops an existing approval; in chat mode, run it once without `--phrase` to obtain the `REVOKE` phrase bound to the approved version, then re-run with `--phrase` and `--user-reply` after the user agrees. `reject` and `revoke` follow the same gate as `confirm`. `review` exposes both the `APPROVE` and `REJECT` phrases; `reject --via chat` accepts only the `REJECT` phrase. When `next` reports a rejection, fix the cited section and re-`approve` it; do not widen the user's reason.
- Write pages only from approved reports. Page format follows Design's slides skill exactly (1920×1080, one `<section>` per file, inline `style` only). Read `references/slides.md` for investment-specific rules: one conclusion per page, the author judgment box only on chapter-closing or user-named key pages, sourced footnotes as `机构或作者《标题》（日期）`, numbers only from `research/numbers.md`, and `[待补：…]` for anything missing.
- The user reviews and hand-edits on 5173. Before changing any page, reread it and edit what is there; never rewrite a page from memory. If `slides build` or a unit command reports a conflict with the open editor, stop and tell the user instead of overwriting.
- Changing a page's layout needs no approval. Changing what a page claims (conclusions, numbers) means changing the report first and getting it re-approved.

## Workflow

1. `my-slides status` and `my-slides sources scan`. Update the Wiki, then `validate wiki` and `sources mark-ingested`.
2. `prepare report --unit <id>` → write `reports/units/<id>.md` → `validate report --unit <id>` → `approve report --unit <id>` (or `--chapter`) → `review report` → paste it and wait → after an explicit user approval, `confirm report --via chat` → `assemble`.
3. `prepare evidence-research` → research public hard figures and record them in `research/numbers.md` → `validate evidence-research`.
4. `prepare slides --unit <id>` → write `my-slides/design/deck/slides/<id>.html` (and `<id>_2.html` … for more pages) following the handoff and `references/slides.md` → `slides build --unit <id>` → `slides check --all`. Self-review against `references/visual-rules.md`.
5. `slides open` → give the user the review link and the host command, then stop. The user reviews on 5173: small fixes by hand, larger ones by telling you. Apply requested changes on the current files, rebuild, and re-check.
6. When the user is satisfied and the host is running: `export [--output DIR]` writes `<project>-v<N>-<date>.html` and records the delivery in `.state/deliveries.json`.

## Useful commands

```text
my-slides doctor
my-slides status
my-slides next --json
my-slides next --all
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
my-slides reject report --unit <id> --reason "结论需要修订" --via chat --phrase "REJECT REPORT <id> <sha12>" --user-reply "..."
my-slides withdraw report --unit <id>
my-slides revoke report --unit <id> --via chat                 # 查看已批准版本与 REVOKE 短语
my-slides revoke report --unit <id> --via chat --phrase "REVOKE REPORT <id> <sha12>" --user-reply "..."
my-slides assemble
my-slides prepare evidence-research
my-slides validate evidence-research
my-slides prepare slides --unit <id>
my-slides slides build --all
my-slides slides check --all [--strict] [--browser]
my-slides slides open
my-slides export [--output <目录>]
```

Use `--project <path>` when the agent's current directory is outside the project.
