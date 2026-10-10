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
- GitHub Actions runs the full regression on PRs; run local tests (`./scripts/run-quick-tests.sh` or the full suite) while developing code changes.
- Keep original investment project sources read-only; agents edit only `my-slides/` outputs inside user projects.
