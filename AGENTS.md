# Repository instructions for coding agents

Read [README.md](./README.md) and [skills/my-slides-workflow/SKILL.md](./skills/my-slides-workflow/SKILL.md) before changing product behavior. This file applies to Cursor, Codex, Claude Code, and any other coding agent working in this repository.

## Versioning (mandatory)

**Every PR into `main` must choose the version level that matches its impact, add a versioned entry to `CHANGELOG.md`, and pass the PR version check.** The check permits exactly one SemVer step from the target branch: patch +1, minor +1 with patch reset to 0, or major +1 with minor/patch reset to 0.

- Patch: compatible additions, bug fixes, and documentation (for example `0.2.10` → `0.2.11`).
- Minor: incompatible changes while the project is on `0.x`, including changed command behavior/arguments, state or manifest format changes, removed commands, or invalidated old approvals (for example `0.2.10` → `0.3.0`). State the reason in the PR description; CI accepts this one-step bump.
- Major (`0.x` → `1.0.0`): only with maintainer approval, recorded by adding the `version:major` PR label.
- A PR that changes only `.github/`, `tests/`, or `scripts/` may skip the version bump. If it bumps anyway, the normal changelog check still applies.
- Add the PR's user-facing notes under the matching non-empty `## [X.Y.Z]` heading in `CHANGELOG.md`, using Added, Changed, Fixed, and/or Breaking Changes sections. CI requires a Breaking Changes section for minor/major steps and rejects that section on a patch step. It does not edit files automatically.
- Development checkouts show the version, short Git commit, and whether tracked or untracked files are modified. Installed packages without repository metadata show only the package version. `my-slides help --json` includes `version`, `commit`, and `dirty` fields. Git metadata is read only for `--version` and `help`.
- After a version bump reaches `main` and tests pass, CI creates and pushes the missing annotated `vX.Y.Z` tags. Do not tag by hand. See [docs/versioning.md](docs/versioning.md).

## Contributing (brief)

- Prefer topic branches and pull requests into `main`.
- GitHub Actions runs the Python test suite on PRs; the Design+Slides engine integration tests skip there because the engine lives in a private repo. Run `./scripts/run-quick-tests.sh` while developing, and `./scripts/run-full-tests.sh` (requires `MY_SLIDES_DESIGN_ROOT`) before changing anything that talks to the Design engine.
- Keep original investment project sources read-only; agents edit only `my-slides/` outputs inside user projects.

## Skill templates (mandatory when editing the skill)

The in-repo skill lives under `skills/my-slides-workflow/` (`SKILL.md`, `references/`, `examples/`). The wheel install mirrors the same trees under `src/my_slides/templates/`. After editing the skill tree, run:

```bash
python scripts/sync-skill-templates.py --force
```

CI and package builds require the mirrors to match. Do not edit only `templates/` — that path drifts and breaks installed projects. `scripts/sync-skill-templates.py --check` reports drift without writing.

## Slides QA expectations

Slides are Design+Slides pages (issue #58). When changing the deck sync, Design checks, examples, or page-writing guidance:

- Page format is owned by Design's own slides skill (`<MY_SLIDES_DESIGN_ROOT>/skills/slides/`); my-slides references add only investment-specific rules. Do not copy Design's format rules into this repo.
- `slides check` (Design structure) is required; `--browser` (Design render check) needs the host running. Visual quality is reviewed by the user on 5173 — do not claim automated visual QA.
- Every example `page.html` must pass the Design check with `--strict`.
- Prefer updating existing references (`references/slides.md`, `charts.md`, `visual-rules.md`) over adding a parallel doc tree.

## Deferred product work (do not implement casually)

figure-spec, interactive slide runtimes, and human reader-comprehension studies are **deferred** after issue #38. Do not add them in drive-by PRs. Open a dedicated issue with reuse evidence and acceptance criteria first. Static diagrams built from Design shapes and connectors, or inline SVG (see `examples/technology/02-batching-static/`), remain the allowed path for hard-to-explain mechanisms.
