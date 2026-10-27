---
name: my-slides-workflow
description: Use a versioned my-slides workspace to hand an investment article to beautiful-article and/or Design+Slides, preserving existing outputs and reporting target results honestly.
---

# My Slides thin workflow

Use for a project with `my-slides/project.json`. First read that file and the referenced article; all paths are relative to the project root. `my-slides init --project <root>` creates a minimal config. Select either or both targets, for example:

```json
{"schema_version":1,"article":"my-slides/article.md","present":{
  "beautiful":{"provider":"beautiful-article","output":"my-slides/beautiful/article.html"},
  "slides":{"provider":"design-and-slides","output":"my-slides/design/deck"}
}}
```

Input stays inside the project; outputs stay inside `my-slides/` and cannot overlap the article, config, or each other. Do not redirect the workspace or put links inside output directories. Additional configuration and migration rules live in the repository's `docs/remake-contract.md`.

## First, then, done

1. Treat original materials as read-only. Use an existing nonempty article or help write `my-slides/article.md` with external writing skills if available. Wiki and Report may be external optional preparation. Keep sources, dates, numeric definitions, and evidence gaps in prose. Do not invent facts or create a new Spec gate.
2. Run `my-slides present --project <root> --json` (or `--target beautiful|slides`). A `pending_agent` result is a handoff: read the named external provider's actual skill and create or revise that target. Preserve current human edits. The CLI does not execute a skill as a subprocess. Missing provider or input is unfinished and returns nonzero.
3. For beautiful, follow the installed beautiful-article skill and inspect its HTML and citations. For slides, read `<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md`; Design owns page format. The output must end in `deck`; use its parent as projects root (`<root>/my-slides/design` above) and `deck` as project. For an online edit, reread pages, check the current baseline, and publish through Design `apply`. A failed connection, timeout, or 409 is not permission to write directly to disk.
4. Run `present` again to get per-target results. Design structural success is only `check --strict`; run the engine's render check and have the user review on 5173 separately. Verify the host serves this project. The CLI always reports `content_sync: unknown`; its fingerprints describe current files, not which article generated a target. Compare the article and presentations yourself, and flag affected targets for updating when the article changes. Beautiful remains `pending_agent` even with an HTML file; explain completion after inspecting it. Content and visual acceptance are human judgments. Only claim a target finished after its actual artifact, checks, and review are complete.

The article is the shared content baseline. A presentation can reorganize or shorten it. If a user changes a claim or number in one presentation, explicitly update the article and then the other target, or mark it as a target-specific difference. Do not silently synchronize, overwrite other targets, or infer approval from an old Report. Retry only the requested target. Failed attempts preserve the last valid artifact. Offline export and external publishing are separate actions.

The 0.7 `project.yaml`/`units.json` CLI workflow has been removed. For a copied old project, migrate the body into `article.md`, add `project.json`, retain old approvals and files as history, and validate before switching. Investment-specific guidance in `references/slides.md`, `charts.md`, and `visual-rules.md` is optional.
