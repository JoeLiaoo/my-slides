# Repository instructions for coding agents

Read [README.md](./README.md) and [skills/my-slides-workflow/SKILL.md](./skills/my-slides-workflow/SKILL.md) before changing product behavior. This file applies to Cursor, Codex, Claude Code, and any other coding agent working in this repository.

## Version bump (mandatory)

**Every PR that merges meaningful code or docs into `main` MUST bump the patch version in `pyproject.toml` `[project].version` in that same PR** (e.g. `0.2.0` → `0.2.1`).

- Do this **before merge**, in the same PR as the change. CI runs tests but does not bump the package version.
- After the bump, `my-slides --version` (editable install) must match `pyproject.toml`.
- Exception: a pure version-bump-only or chore PR that already bumped. If the PR has no user-visible change, still prefer bumping when anything lands on `main` so `--version` tracks freshness.
- Minor/major bumps only when a human explicitly asks.

## Contributing (brief)

- Prefer topic branches and pull requests into `main`.
- GitHub Actions runs the full regression on PRs; run local tests (`./scripts/run-quick-tests.sh` or the full suite) while developing code changes.
- Keep original investment project sources read-only; agents edit only `my-slides/` outputs inside user projects.
