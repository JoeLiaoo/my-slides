# Changelog

Notable user-facing changes to My Slides.

## [Unreleased]

No unreleased changes.

## [0.4.3] - Pending

### Added

- `my-slides chapters list/add/rename/remove/move` 管理项目报告大章节。`add` 顺序追加或插入到指定章节之后；`rename` 同时更新 `project.yaml`、`units.json`、`wiki/index.md`，报告与 Spec 批准绑定的内容哈希与依赖指纹不变，无需重新批准；`remove` 在仍有小章节引用时拒绝；`move` 调整顺序并验证 `units.json` 跟随新顺序。`chapters list` 额外报告 units.json 引用但 project.yaml 之外的孤儿章节。
- `my-slides export [--output DIR]` 校验整套 Slides 后导出 `<项目名>-v<序号>-<日期>.html`，并在 `.state/deliveries.json` 记录交付时间、版本、包含单元与各单元 SHA-256。若报告、Spec、HTML 构建或检查不是最新版本则拒绝，并列出需要补齐的小章节。
- `status --json` 增加 `delivery` 字段，包含最近一次交付记录与自该交付以来变化的单元（按报告、Spec、HTML 哈希分别列出原因）；没有交付时返回 `has_delivery: false`。

## [0.4.2] - Pending

### Fixed

- `next` no longer recommends re-approving a unit whose latest decision was rejected when the on-disk content already matches the previously approved version. The status/next gates now match: a rejection is only actionable while the unit is neither approved nor pending; restoring the approved content (or re-submitting) clears the actionable rejection without losing the decision history.
- Chat-mode `reject --via chat` now requires a dedicated `REJECT <KIND> <target> <digest[:12]>` phrase bound to the pending version, mirroring the `REVOKE` phrase used by `revoke`. `review` exposes both the `APPROVE` and `REJECT` phrases bound to the same pending version so the agent can paste either into the conversation; reusing an `APPROVE` phrase to decline (or vice versa) is rejected.
- The human-readable text output of `review` now prints the `驳回短语` line right after the `确认短语`, so chat-mode rejection is usable when an agent pastes the plain (non-JSON) review output into the conversation.

### Changed

- Chat-mode `revoke --via chat` now allows withdrawal when an `approved_sha256` exists even if the on-disk content has since diverged, so a user can drop a stale approval that the file edit invalidated. `refresh_unit_currency` and the binding already used `approved_sha256`; the gate now matches.
- The `review` packet adds a `reject_phrase` field alongside `phrase`; CLI help for `reject --phrase` and the README/skill/agent-help templates describe the REJECT phrase format.

## [0.4.1] - Pending

### Added

- `reject report|spec --unit <id> --reason "..."` clears a pending approval request and records the user's rejection with the reason, time, channel, and account. In chat approval mode it requires `--via chat` with a matching `--phrase` and `--user-reply`, mirroring `confirm`. In terminal approval mode it requires an interactive TTY the same way `confirm` does. The rejection only declines the current pending version; an existing approval stays in place until the user revokes it.
- `withdraw report|spec --unit <id>` lets the agent cancel its own pending approval request with no user gate. It errors when no request is pending and never records a user decision.
- `revoke report|spec --unit <id> [--reason ...]` lets the user drop an existing approval. In chat mode it uses a dedicated `REVOKE <KIND> <target> <sha12>`-style phrase bound to the current approved version (unit id, chapter, approved_sha256, and the Spec's bound report_sha256). Running it once without `--phrase` prints (or returns in `--json`) the approved version summary plus the phrase the user must agree to, and records nothing; running it again with `--phrase` and `--user-reply` after the user agrees performs the revocation. Terminal mode requires an interactive TTY. Revoking a report also invalidates the bound Spec approval and the unit's HTML/check state; revoking a Spec invalidates HTML/checks. Approved copies in `.state/approved/` are kept.

- `status` lists `rejected_units` and `rejections` (including reason, account, and channel) per unit. `next` recommends `review` when a unit is pending again after rejection; the rejection-only recommendation appears when no new request has been submitted. Re-submitting after a rejection resets `latest_decision` so `next` does not loop on the same recommendation. Rejection and approval entries are preserved in `decision_history` for traceability.

### Changed

- State files gain `latest_decision`, `latest_rejection`, and `decision_history` per kind. Existing state files without these fields load as before; `refresh_unit_currency` keeps producing the same current flags until a new decision is recorded. `record_rejection` no longer touches existing approved_sha256, the bound Spec approval, or HTML/check state — the rejection is a decision about the pending version only, and `refresh_unit_currency` continues to drive downstream currency.

## [0.4.0] - Pending

### Breaking Changes

- The default approval channel is now the agent conversation. `next` asks for `review` instead of a terminal `confirm`. Set `approval_mode: terminal` in `project.yaml` to keep the interactive-terminal gate.

### Added

- `review report|spec` shows the pending section or chapter, the text under review, a concrete diff when an approved copy exists, and the confirmation phrase. Report diffs longer than 40 lines say they were truncated.
- The confirmation phrase is bound to the section chapter, dependency fingerprint, and, for a Spec, the approved report version. A phrase from an earlier chapter or dependency context cannot confirm a later request.
- `confirm --via chat --phrase ... --user-reply ...` records a conversation approval. `approve --chapter` and `confirm --chapter` submit and confirm every section in one chapter; each section keeps its own approval record.
- `project.yaml` accepts `reviewer` and `approval_mode`. `init --force` keeps both settings.

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
