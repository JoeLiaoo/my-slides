# Changelog

Notable user-facing changes to My Slides.

## [Unreleased]

No unreleased changes.

## [0.3.0] - Pending

### Breaking Changes

- A unit is now a section that may contain multiple slides. Specs use consecutive `## Slide N —` pages (a cover stays one page; other sections allow up to 8). HTML page count must match the Spec, and each page may use only the charts and icons declared on that Spec page. Decks number slides across the whole presentation and record `data-unit-page`.

### Added

- `units add --title` and `units retitle` store a section display name such as 需求分析. Retitling does not revoke report or Spec approval.

### Changed

- Existing one-page Specs that identify themselves with `页面 ID` remain valid. `单元 ID` at the top of a Spec is the preferred form.

## [0.2.12] - Pending

### Added

- Add `units add`, `move`, `rename`, `remove`, `restore`, and `trash list`. Removal previews the effect and, with `--yes`, moves the unit into recoverable `.state/trash/`.
- `units move` can append to a chapter, including an empty one, or use `--before` to place a unit first in that chapter.

### Changed

- A cross-chapter move asks the user to reconfirm the report while keeping an unchanged Spec approval. Same-chapter reordering and a mechanical rename keep both approvals. Structural changes require rebuilding and rechecking the deck.

## [0.2.11] - Pending

### Added

- Add a versioned changelog, impact-based SemVer guidance, and PR CI checks for one-step version changes and matching changelog entries.
- Show the short Git commit and dirty-worktree indicator in development `--version` output; include `commit` and `dirty` in `help --json`.

### Changed

- After tests pass on `main`, CI creates annotated `vX.Y.Z` tags for versions that do not have one yet. Pull requests that only change `.github/`, `tests/`, or `scripts/` may skip the version bump. A follow-up check fails a merge that lands without a version advance outside that set.

## [0.2.10]

### Breaking Changes

- `approve report/spec` now submits a pending request; the user must review and run `confirm` in an interactive terminal. Older approvals without reviewer identity must be confirmed again.

### Changed

- Split the v2 CLI into focused command modules and document a user-centered acceptance test plan.

## [0.2.9]

### Changed

- Clarify public setup, prerequisites, and GitHub Actions guidance in the README and project plan.

## [0.2.8]

### Added

- Adopt the MIT license and add a GitHub Actions full-regression workflow.

## [0.2.7]

### Added

- Document Python, Node.js, renderer, and browser prerequisites for installation and use.

## [0.2.6]

### Fixed

- Count slide pages by the `slide` class token so class order and additional classes do not cause incorrect counts.

## [0.2.5]

### Changed

- Apply the editorial-light slide shell consistently to previews and assembled decks.

## [0.2.4]

### Added

- Add `my-slides help` with a bundled first-use workflow guide for agents.

## [0.2.3]

### Fixed

- Correct report approval currency, dependency-aware cache reuse, and browser-check fingerprints.

Version `0.2.2` was never assigned or released. The version sequence moved directly from `0.2.1` to `0.2.3`; there is no `v0.2.2` tag.

## [0.2.1]

### Changed

- Document the requirement to update the package version for each PR merged to `main`.

## [0.2.0]

### Changed

- Complete the transition to the v2 unit workflow and remove the unsupported legacy chapter workflow.
