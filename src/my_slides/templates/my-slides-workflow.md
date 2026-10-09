---
name: my-slides-workflow
description: Use the local my-slides CLI to maintain an investment project's Markdown Wiki, prepare and validate an investment report and Presentation Spec, and build offline HTML slides.
---

# My Slides investment workflow

Use this skill when working inside an investment project that contains `my-slides/project.yaml`.

**Prefer v2.** New projects from `my-slides init` are v2 (`units.json` + unit directories). If `my-slides/units.json` exists, run `my-slides units list` and `my-slides status --json` first. Use `--unit <id>` (or `--changed` / `--all`) with `prepare` / `validate` / `approve` / `slides build` / `slides check`. Assemble the full report with `my-slides assemble` after unit report approvals.

Projects without `units.json` are unsupported. Legacy chapter migration is unsupported; re-`init` for a v2 project.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the configured report chapter themes and their order (Wiki index / `project.yaml` chapters). In v2, delivery structure comes from `units.json`.
- State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- Never approve a report or Spec on the user's behalf; approval commands record an explicit user review decision.
- Generate HTML only from approved Specs. Write one content fragment per unit using the component examples from `prepare slides`. Keep custom styles scoped; include one `slide-notes` JSON block on every slide. Use only approved `echarts-spec` and Lucide markers. Do not use a CDN. The editorial-light shell, fonts, and navigation are added by `slides build` into `slides/previews/<id>.html` and `slides/index.html`.

## v2 workflow

1. `my-slides status` and `my-slides sources scan`. Update Wiki, then `validate wiki` and `sources mark-ingested`.
2. `prepare report --unit <id>` → write `reports/units/<id>.md` → `validate report --unit <id>` → user review → `approve report --unit <id>`. Optionally `assemble`.
3. `prepare spec --unit <id>` → write one-page Spec in `specs/units/<id>.md` (page ID = unit ID) → validate → user review → `approve spec --unit <id>`.
4. `prepare slides --unit <id>` → write `slides/pages/<id>.html` → `slides build --unit <id>` → `slides check --unit <id> --browser`.

## Useful commands

```text
my-slides status
my-slides sources scan
my-slides prepare wiki [--question "..."]
my-slides validate wiki
my-slides sources mark-ingested
my-slides units list
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>
my-slides assemble
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id> --browser
```

Use `--project <path>` when the agent's current directory is outside the project.
