# Versioning and tags

## Selecting a version

Use the project version in `pyproject.toml` and add a matching heading and user-facing notes to `CHANGELOG.md` in the same PR.

- Compatible additions, bug fixes, and docs increment the patch: `0.2.10` → `0.2.11`.
- A pull request that only changes `.github/`, `tests/`, or `scripts/` may leave the version unchanged. Bumping it is still allowed and then requires a changelog entry.
- Incompatible changes on `0.x` increment the middle number and reset patch: `0.2.10` → `0.3.0`. Examples include changing existing command behavior or arguments, changing state or manifest formats, removing commands, or invalidating old approvals.
- A `0.x` → `1.0.0` major release is a maintainer decision. Add the `version:major` label to the PR to authorize that version step in CI.

The PR version check accepts exactly one next step: patch +1, minor +1 with patch 0, or—only with the maintainer label—major +1 with minor and patch 0. It requires a non-empty `## [X.Y.Z]` section for the proposed version. Minor/major steps require a `### Breaking Changes` (or `### 不兼容变更`) subsection, while a patch step must not use that subsection. It skips the check when the version is unchanged and every changed file is under `.github/`, `tests/`, or `scripts/`. It does not choose the version level or edit files for the PR author.

## Version output

In a source checkout, `my-slides --version` displays the package version, seven-character Git commit, and a dirty marker when the checkout has modified or untracked files. Other commands do not query Git. The package's `help --json` output contains `version`, `commit`, and `dirty`. Formal installs without the source `pyproject.toml` or usable Git metadata fall back to the package version only.

## Tags after merge

CI tags releases. The test job stays read-only. After it passes on `main`, a separate job with `contents: write` does two things:

1. Compare the pushed `main` with the previous commit. If the version did not move and the push changed more than `.github/`, `tests/`, or `scripts/`, the job fails. This catches two pull requests that both passed the check against the same base version and then merged without a further bump.
2. Walk first-parent history, find the first commit that introduced each `X.Y.Z` version, and create an annotated `vX.Y.Z` tag when that tag is missing. Existing tags that already point at those commits are left alone. A tag that points somewhere else fails the job instead of being moved. The tag message is the changelog section when one exists.

Do not create tags by hand, and do not tag a pull request before it merges. The repository must allow Actions to write contents (Settings → Actions → General → Workflow permissions); otherwise the tag job fails after tests have already passed.

## Historical tags

Tags `v0.2.0`–`v0.2.10` were created before automatic tagging, each on the first `main` commit whose `pyproject.toml` introduced that version. There is no `v0.2.2`. The tag job still checks this mapping and only adds versions that do not have a tag yet, including `v0.1.0` if it is missing:

| Tag | First commit with that version |
| --- | --- |
| `v0.2.0` | `26951e4f87d7d0f3d8ca52ec1e34adaf11529d42` |
| `v0.2.1` | `f2e89a9a62f162f82d7d64d055162aa0b1eab263` |
| `v0.2.2` | Not assigned; no tag |
| `v0.2.3` | `4f76e8639fa23672f7df313ce5121c06fbe3cfd7` |
| `v0.2.4` | `818abf06afc9d5ff7d28189dc198af5a7140c085` |
| `v0.2.5` | `01aac4a8af929a9e28e221d944219a22a4ff0c01` |
| `v0.2.6` | `babb53081550c89a250aa7152d45d915c4ffafdb` |
| `v0.2.7` | `1765e8b3780f18e4922eb0b237f0399a6aa24fca` |
| `v0.2.8` | `ec02c76031812fb6fc700e3b6883180f1d89892f` |
| `v0.2.9` | `d8fb72e9385bc9ccf22e94e52e7ce2534bb5fdb8` |
| `v0.2.10` | `2c770917c6418abb1992e8a5f4b703c165f6fb20` |
