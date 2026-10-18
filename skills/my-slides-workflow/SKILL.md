---
name: my-slides-workflow
description: Use the local my-slides CLI to maintain an investment project's Markdown Wiki, prepare and validate an investment report and Presentation Spec, build offline HTML slides, and pick reference examples and visual rules by communication problem.
---

# My Slides investment workflow

Use this skill when working inside an investment project that contains `my-slides/project.yaml`.

Projects use `units.json` and unit directories (created by `my-slides init`). Run `my-slides units list`, `my-slides status --json`, and `my-slides next --json` first. `next` returns a command, target unit, reason, and `actor`. Use `--unit <id>` (or `--changed` / `--all`) with `prepare` / `validate` / `approve` / `slides build` / `slides check`. Assemble the full report with `my-slides assemble` after unit report confirmations.

Projects without `units.json` need `my-slides init` before other commands.

`slides check` without `--browser` is structural only (unit set/order, cover). Add `--browser` after `my-slides browser install` for viewport QA.

`prepare` updates fixed files in `my-slides/work/` (`wiki.md`, `wiki-question.md`, or `<kind>/<unit-id>.md`). Reuse the returned path; repeated preparation does not create new timestamped handoffs.

`prepare slides` also surfaces the 1–2 most relevant reference example paths for the current Spec; read the index below to see how queries are matched. It does not dump the full example library into context.

After report assembly and before drafting Specs, run `my-slides prepare evidence-research` and complete `my-slides/research/numbers.md` with sourced public figures. Run `my-slides validate evidence-research`; `next` recommends this phase when the list is missing or invalid. Cite an ID only when its number directly supports that page's conclusion; each ID may appear at most once across the deck. A page without a relevant figure may use a table or structural diagram and omit numeric IDs. ECharts data must map to listed IDs.

## On-demand references

This skill entry stays short. Read the references below only when the step you're about to do actually needs them. The packaged install mirrors this layout under `my-slides/templates/references/` for wheel users; resolve the path with the same relative layout.

| When you are about to … | Open |
| --- | --- |
| Read or update the project Wiki | `references/wiki.md` |
| Write a report section | `references/report.md` |
| Write or validate a Spec page (内容类型 / 版式 / 布局意图) | `references/spec.md`, `references/example-index.md` |
| Convert an approved Spec into HTML | `references/slides.md` |
| Choose a chart type or sanity-check data | `references/charts.md` |
| Pick a layout / find a reference example | `references/example-index.md` |
| Author in the bundled editorial-light theme | `references/editorial-light-theme.md` |
| Review layout variety and page density before delivering | `references/visual-rules.md` |

The reference set is fixed and shared between the in-repo `skills/my-slides-workflow/` and the packaged `src/my_slides/templates/` mirror. `scripts/sync-skill-templates.py` is the single point that keeps both copies in step; CI and the package build rely on it. Do not hand-edit `templates/` only — that path falls out of sync and breaks the wheel install.

## Repository version bump (when changing this package)

For a PR into the **my-slides** repo `main`, select a version step that matches impact, add a matching `CHANGELOG.md` entry, and let PR CI validate both. Compatible additions, fixes, and docs use patch +1; incompatible changes on 0.x use minor +1 and reset patch to 0, with a Breaking Changes section in the changelog. A major bump requires the maintainer's `version:major` PR label. PRs that only change `.github/`, `tests/`, or `scripts/` may skip the bump. Development `--version` output includes the short commit and dirty state; installed packages without Git metadata show only the version. After tests pass on `main`, CI creates and pushes the annotated `vX.Y.Z` tag. See repo-root `AGENTS.md` and `docs/versioning.md`.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the configured report chapter themes and their order (Wiki index / `project.yaml` chapters). Delivery structure comes from `units.json`.
- Use `my-slides units add/move/rename/remove` for inventory changes; never edit `units.json` manually. `units move` accepts `--after` or `--before`; omit both to append to the target chapter, including a chapter that currently has no units. A chapter-only move requires report reconfirmation, while an unchanged report keeps its Spec approval. Same-chapter order changes and renames require rebuilding the full deck and rerunning checks.
- Use `my-slides chapters list/add/rename/remove/move` to keep `project.yaml`, `units.json`, and `wiki/index.md` in sync. Renaming only relabels the chapter field on affected units, so report and Spec approvals stay bound to unchanged content hashes and dependency fingerprints and do not need a new approval; rebuilding the full deck and rerunning checks is still required. Removing a chapter that still has units is refused.
- After every unit and chapter is approved, built, and checked, run `my-slides export [--output DIR]`. The command verifies every unit's report, Spec, HTML, and browser check are still current, copies `slides/index.html` to `<project>-v<N>-<date>.html`, and appends an entry to `.state/deliveries.json` (time, package version, units and their SHA-256). `status --json` shows the most recent delivery and which units changed since.
- `my-slides units remove <id>` is a read-only impact preview. Review its files, approvals, dependencies, and Markdown references before using `--yes`. Removal is recoverable, so an Agent may run `--yes`, but if the preview shows any prior report or Spec approval, first ask the user for explicit consent. Never remove a blocked unit. Include the printed `my-slides units restore <trash-id>` command in the result; use `units trash list` to find other recoverable entries. Trash is not part of source scans or delivery.
- State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- `approve report/spec` only submits a pending review request. When `next` returns `actor: human`, run the suggested `review` command, paste its output into the conversation, and stop. On the user's next message, run `confirm --via chat` only if that message explicitly approves the named section or chapter. Pass that message unchanged as `--user-reply`. Do not treat "continue", "looks fine", or "next" as approval, and do not widen the scope. Never invent a phrase: copy it from the latest `review`. Never run `confirm` through a pseudo-terminal or input automation (`script`, `expect`, tmux `send-keys`, piping answers). If `project.yaml` sets `approval_mode: terminal`, do not run `confirm` at all; ask the user to run it in their own terminal.
- The user can also reject or revoke. `reject report|spec --unit <id> --reason "..."` clears the pending request and records the reason; it only declines the current pending version and never invalidates an already approved report or Spec. `withdraw report|spec --unit <id>` is for the agent to drop one of its own requests and never counts as a user decision. `revoke report|spec --unit <id> [--reason ...]` drops an existing approval; in chat mode, run it once without `--phrase` to obtain the `REVOKE` phrase bound to the approved version, then re-run with `--phrase` and `--user-reply` after the user agrees. Revoking a report also invalidates the unit's Spec approval and HTML/check chain. All three follow the same gate as `confirm`/`review` for chat phrase binding, and `reject`/`revoke` additionally require `--via chat` (or an interactive terminal in `approval_mode: terminal`). When `next` reports a rejection as the latest state, fix the cited section and re-`approve` it; do not widen the user's reason. `review` exposes both the `APPROVE` and `REJECT` phrases bound to the same pending version, and `reject --via chat` accepts only the `REJECT` phrase; never reuse an `APPROVE` phrase to decline.
- After the Wiki is ready, propose a 大章节 → 小章节 outline in the conversation (for example 行业分析 / 需求分析, 竞争分析). Create each section with `units add <id> --chapter <大章节> --title <小章节名>` only after the user accepts the outline. `units retitle` changes the display name and keeps existing approvals.
- Generate HTML only from approved Specs. One unit is one section and may contain multiple slides: the HTML page count must equal the Spec's `## Slide N` count (cover is one page; a content section has at most 8). Keep custom styles scoped; include one `slide-notes` JSON block on every slide. A slide may use only the `echarts-spec` and Lucide icons declared on that same Spec page. Do not use a CDN. The editorial-light shell, fonts, and navigation are added by `slides build` into `slides/previews/<id>.html` and `slides/index.html`. Changing only slide layout does not require a new approval; changing Spec content requires re-approval of that section only.
- Every Spec page declares one content type and one layout from `references/example-index.md`. The same layout can appear at most twice in a row; the deck uses at least `min(3, total pages)` distinct layouts. Every content page cites numbers only when they directly support its conclusion, and each number ID may appear once across the deck. A no-number page may use a table or structural diagram. Add the author-owned `我们的判断 / 对投资的含义` box only to chapter closing pages or pages marked `关键页：是`. Guest or interview quotes are evidence only. Put estimates, unverified status, and data definitions in the page footnote, normalize each citation as `机构或作者《标题》（日期）`, and state each estimate/scope once.
- Every Spec page must fill the 布局意图 sub-points (读者问题 / 唯一结论 / 关系类型 / 主视觉 / 阅读顺序 / 选这个形式的原因); an empty critical section is a validation error before approval. Read `references/spec.md` for the structure and worked examples.

## Workflow

1. `my-slides status` and `my-slides sources scan`. Update Wiki, then `validate wiki` and `sources mark-ingested`.
2. `prepare report --unit <id>` → write `reports/units/<id>.md` → `validate report --unit <id>` → `approve report --unit <id>` (or `--chapter`) → `review report` → paste it and wait → after an explicit user approval, `confirm report --via chat` → `assemble`.
3. `prepare evidence-research` → research public hard figures and record them in `research/numbers.md` → `validate evidence-research`. Reference an ID only on the single page where it best supports the conclusion; omit IDs when no relevant figure exists. Use no unlisted values in charts.
4. `prepare spec --unit <id>` → write the section Spec in `specs/units/<id>.md` (one `## Slide N —` block per page; `单元 ID` equals the unit ID; each page declares content type and an example-backed layout; a legacy `页面 ID` line is still accepted) → validate → `approve spec` → `review spec` with the variety/density rubric in `references/visual-rules.md` → paste it and wait → after an explicit user approval, `confirm spec --via chat`.
5. `prepare slides --unit <id>` (it appends the 1–2 most relevant reference example snippets to the handoff) → write `slides/pages/<id>.html` with one `<section class="slide">` per Spec page → `slides build --unit <id>` → `slides check --unit <id>` (structural) → for delivery QA, `slides check --all --browser --screenshots`, open contact sheets, then `slides visual-review` with layout variety and per-page density scores and observations. Render the author-voice box only where Spec requires it; keep source footnotes and evidence close to their claim. Optional page `metric-spec` and chart rules: `references/charts.md`. Re-check `references/visual-rules.md` before reporting done. figure-spec / interactive runtimes are deferred; use static SVG only when text cannot explain the mechanism (see `examples/technology/02-batching-static/`).

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
my-slides reject report --unit <id> --reason "结论需要修订" --via chat --phrase "REJECT REPORT <id> <sha12>" --user-reply "..."
my-slides withdraw report --unit <id>
my-slides revoke report --unit <id> --via chat                 # 查看已批准版本与 REVOKE 短语
my-slides revoke report --unit <id> --via chat --phrase "REVOKE REPORT <id> <sha12>" --user-reply "..."
my-slides assemble
my-slides prepare evidence-research
my-slides validate evidence-research
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides review spec --chapter <大章节>
my-slides confirm spec --chapter <大章节> --via chat --phrase "APPROVE SPEC <大章节> <sha12>" --user-reply "<用户原话>"
my-slides reject spec --chapter <大章节> --reason "..." --via chat --phrase "REJECT SPEC <大章节> <sha12>" --user-reply "..."
my-slides withdraw spec --unit <id>
my-slides revoke spec --chapter <大章节> --via chat               # 查看 REVOKE 短语
my-slides revoke spec --chapter <大章节> --via chat --phrase "REVOKE SPEC <大章节> <sha12>" --user-reply "..."
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id>
my-slides slides check --unit <id> --browser
my-slides slides check --all --browser --screenshots
my-slides slides visual-review --unit <id> --images contact-desktop.png contact-mobile-portrait.png contact-mobile-landscape.png --notes "观察与修订结论"
```

Use `--project <path>` when the agent's current directory is outside the project.
