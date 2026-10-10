# Versioning and tags

## Selecting a version

Use the project version in `pyproject.toml` and add a matching heading and user-facing notes to `CHANGELOG.md` in the same PR.

- Compatible additions, bug fixes, docs, tests, and CI changes increment the patch: `0.2.10` → `0.2.11`.
- Incompatible changes on `0.x` increment the middle number and reset patch: `0.2.10` → `0.3.0`. Examples include changing existing command behavior or arguments, changing state or manifest formats, removing commands, or invalidating old approvals.
- A `0.x` → `1.0.0` major release is a maintainer decision. Add the `version:major` label to the PR to authorize that version step in CI.

The PR version check accepts exactly one next step: patch +1, minor +1 with patch 0, or—only with the maintainer label—major +1 with minor and patch 0. It requires a non-empty `## [X.Y.Z]` section for the proposed version. Minor/major steps require a `### Breaking Changes` (or `### 不兼容变更`) subsection, while a patch step must not use that subsection. It does not choose the version level or edit files for the PR author.

## Version output

In a source checkout, `my-slides --version` displays the package version, seven-character Git commit, and a dirty marker when the checkout has modified or untracked files. The package's `help --json` output contains `version`, `commit`, and `dirty`. Formal installs without the source `pyproject.toml` or usable Git metadata fall back to the package version only.

## Creating tags after merge

Tagging stays manual so Actions can keep read-only `contents` permissions. After a version bump reaches `main`, a maintainer can run:

```bash
git switch main
git pull --ff-only
VERSION=$(python3 -c 'import tomllib; print(tomllib.loads(open("pyproject.toml", "rb").read().decode())["project"]["version"])')
git tag -a "v${VERSION}" -m "my-slides ${VERSION}"
git push origin "v${VERSION}"
```

Do not create a tag for a PR before it is merged. The annotated tag should point to the merge commit containing that version.

## Historical tags

The repository had no tags before this policy. Backfill each historical tag to the first commit whose `pyproject.toml` introduced that version:

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

Create an annotated tag for each assigned version with `git tag -a vX.Y.Z <commit> -m "my-slides X.Y.Z"`, then push each exact tag with `git push origin vX.Y.Z`. Do not create `v0.2.2`.
