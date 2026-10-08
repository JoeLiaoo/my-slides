---
name: my-slides-workflow
description: Use the local my-slides CLI to maintain an investment project's Markdown Wiki, prepare and validate an investment report and Presentation Spec, and build offline HTML slides.
---

# My Slides investment workflow

Use this skill when working inside an investment project that contains `my-slides/project.yaml`.

If `my-slides/units.json` exists, the project is **v2 unit format**. Run `my-slides units list` and `my-slides status --json` first. Use `--unit <id>` (or `--changed` / `--all`) with `prepare` / `validate` / `approve` for report and Spec. Do not use chapter-wide approve/build commands on v2 projects. Unit-level slides build/check arrive in later steps; assemble the full report with `my-slides assemble` after unit report approvals.

## Working rules

- Treat original project documents as read-only. The CLI scans Markdown sources; the agent reads them and edits only `my-slides/` outputs.
- Read `my-slides/wiki/README.md` and `my-slides/wiki/index.md` before updating or querying the Wiki. Use ordinary Markdown and links. Do not invent tags, frontmatter, per-source IDs, or fact/forecast classifications.
- Keep the six configured report chapters and their order. State evidence gaps, conflicting figures, assumptions, and dates in natural prose.
- Prepare the report from the Wiki and linked sources. Run validation and ask the user to review the complete report before `my-slides approve report`.
- Build a page-by-page Spec from the approved report. Preserve argument order and map substantive report sections to slides. Keep chart data explicit and sourced. Ask the user to review the Spec before `my-slides approve spec`.
- Generate chapter HTML only from the approved Spec. Keep styles scoped to each chapter; include one `slide-notes` JSON block on every slide. Use only the approved `echarts-spec` and Lucide icon markers for generated assets. Do not use a CDN.
- Run `my-slides slides build` and `my-slides slides check --browser`. Fix all validation errors before delivery.

## Workflow

1. Run `my-slides status` and `my-slides sources scan`. Read the listed new or changed Markdown sources. Update relevant Wiki pages, links, `wiki/index.md`, and append a short entry to `wiki/log.md`. Run `my-slides validate wiki`, then `my-slides sources mark-ingested`.
2. Run `my-slides prepare report`. Follow its handoff and the bundled chapter template to write one Markdown file per configured report chapter. Validate it, resolve broken references, then present it for user review. After explicit approval, run `my-slides approve report`.
3. Run `my-slides prepare spec`. Write one page block per slide in `my-slides/specs/`, including purpose, conclusion, displayed content, evidence and links, material qualifications, report mapping, layout, and icon needs. Include constrained `echarts-spec` JSON only when it improves the argument. Validate and request user review; then run `my-slides approve spec`.
4. Run `my-slides prepare slides`. Write chapter fragments under `my-slides/slides/chapters/`; use the handoff's page boundaries, design requirements, notes schema, and approved chart/icon payloads. Run `my-slides slides build`, then `my-slides slides check --browser`. Deliver `my-slides/slides/index.html` and report validation results.

## Useful commands

```text
my-slides status
my-slides sources scan
my-slides prepare wiki [--question "..."]
my-slides validate wiki
my-slides sources mark-ingested
my-slides prepare report
my-slides validate report
my-slides approve report
my-slides prepare spec
my-slides validate spec
my-slides approve spec
my-slides prepare slides
my-slides slides build
my-slides slides check --browser
```

Use `--project <path>` when the agent's current directory is outside the project. Never approve a report or Spec on the user's behalf; approval commands record an explicit user review decision.
