# Issue 28 — Phase 1: Unit management design

Status: design proposal for review. No project-manifest or approval-state behavior has changed yet.

## Scope

This phase adds safe CLI operations for the ordered unit inventory in `my-slides/units.json`:

- `my-slides units add <id> --chapter <chapter> [--after <id>] [--role content]`
- `my-slides units remove <id>`
- `my-slides units move <id> --after <id> [--chapter <chapter>]`
- `my-slides units rename <old-id> <new-id>`
- `my-slides units restore <trash-id>`

It also reports orphaned per-unit artifacts and makes CLI assembly use the same manifest validation as the other project commands. The low-level `assemble_report()` remains a pure file/link assembler; command entry points validate the manifest and current approvals before writing a formal report.

Approval history, diff/reject/withdraw/revoke, chapter-management commands, delivery/export, cleanup, and browser-check policy remain separate later phases in Issue 28.

## Invariants

1. Every operation loads and validates the complete manifest against `project.yaml` before planning changes, then validates the proposed manifest before writing anything.
2. Unit IDs stay unique and regex-safe; exactly one cover remains at array index zero; units remain grouped in configured chapter order.
3. An omitted `--after` inserts a content unit after the last unit in its requested chapter, or before the first later configured chapter. `--after` is only valid for an existing unit in the requested chapter. Commands reject ambiguous or invalid insertion points rather than silently reordering unrelated chapters.
4. A new unit receives visible TODO skeletons for its report, one-page Spec, and HTML fragment. Skeletons are not treated as validated or approved content.
5. Same-chapter reordering preserves report and Spec approvals, but invalidates deck-level browser checks because slide order changed. Moving a unit to another chapter invalidates that unit's report and Spec approvals as well as its HTML and checks.
6. Renaming preserves content files and moves the state record for audit, but clears current report/Spec approval bindings. The new identity must be reviewed again. HTML and browser checks are invalidated.
7. Removing a unit never unlinks its content permanently. It moves that unit's report, Spec, page, preview, state, and dependency sidecar into a timestamped `.state/trash/<operation-id>/` directory with a manifest of original paths and hashes. `restore <trash-id>` restores them only when destination paths are free and the resulting manifest is valid.
8. Structural changes invalidate aggregate outputs without deleting them. Keep the last `reports/report.md` and `slides/index.html` available as prior output, mark the deck build/check state stale, and make `next` recommend reassembly/rebuild before completion. Record the manifest identity used for the last formal deck so a changed unit order is detectable. Cached HTML remains content-addressed and can be reused only if the ordinary cache-key checks still pass.
9. Orphan detection covers per-unit files in `reports/units`, `specs/units`, `slides/pages`, `slides/previews`, `.state/units`, and `reports/units/*.depends-on.json` whose IDs are absent from the manifest. It does not treat cache, snapshots, or trash as active unit artifacts.

## Transaction and recovery model

Each mutation follows the same sequence:

1. Read the manifest, config, known unit files, sidecar dependencies, and target paths; build a human-readable operation plan.
2. For removal, print affected artifacts and approval state. Require an explicit second-step `--yes` to apply the reversible move.
3. Stage the new manifest and any rewritten files in a temporary directory under `.state/`.
4. Move files with `Path.replace` while recording each completed move. If a move or validation fails, roll completed moves back in reverse order and leave `units.json` unchanged.
5. Atomically replace `units.json` last. Only after that succeeds, remove staging data and report the trash ID, changed units, and invalidated approvals/checks. Preserve aggregate outputs at their normal paths; invalidation is represented in state and recomputed against the new manifest.

The trash manifest maps every saved unit path to its original project-relative path and SHA-256. The restore command refuses collisions; it never overwrites user files. Operations must remain confined to the `my-slides/` workspace after path resolution.

This gives recoverable file moves and atomic manifest publication. It does not claim a filesystem-wide atomic transaction across power loss; an interrupted staging operation is reported by `doctor` with its recovery directory.

## Operation details

### Add

Validate ID, chapter, role, and placement. Create report, Spec, and page skeletons under their canonical unit paths and insert the unit at the calculated position. Adding a second cover is rejected; the initial cover remains `cover` unless a later explicit rename operation is requested.

### Remove

Show the report, Spec, page, preview, unit state, dependency declaration, and any current approval/check flags. `--yes` performs the move to trash. Reject removal of the only cover or removal that would leave an invalid inventory. Remove references to the deleted unit from dependency sidecars only when the user has confirmed the operation; list each changed dependent unit and invalidate its report approval because its declared dependency set changed.

### Move

Move the entry within its chapter or to a specified chapter while preserving manifest validity. Same-chapter moves preserve report/Spec content approvals and invalidate the assembled deck and browser checks. Cross-chapter moves clear current approval bindings for the moved unit and invalidate its HTML/check state; dependent report approvals are invalidated when their dependency closure changes.

### Rename

Require a free destination ID. Migrate the report, Spec, page, preview, state, and dependency sidecar; update the Spec `页面 ID`, page root `data-unit-id`, and exact unit IDs in dependency sidecars. Rewrite local Markdown links inside `my-slides/` that target the old unit's canonical report/Spec/page paths. Do not globally replace arbitrary prose containing the old ID. Clear current report/Spec approval bindings and HTML/check state; record old/new IDs in the operation manifest.

## Test plan for implementation PR

- Add places units within a chapter and before the next chapter; rejects duplicate IDs, unknown chapters, invalid roles, and a second cover.
- Removes into trash, exposes affected approvals/dependents, refuses without `--yes`, restores successfully, and refuses restore collisions.
- Same-chapter move preserves report/Spec approvals and invalidates checks; cross-chapter move invalidates the moved unit's approvals.
- Rename migrates files and declared dependencies, rewrites only supported metadata/links, clears approvals, and rebuilds under the new ID.
- Orphan reporting finds each supported orphan path and ignores cache/trash.
- Invalid manifest edits never partially change the manifest or lose files; CLI `assemble` rejects a manifest/order mismatch just like `doctor`, `next`, and `slides check`.
- Keep existing report/Spec/HTML dependency and browser-check regression tests passing.

## Review decisions requested

Please review the phase boundary, the invalidation rules for moving/renaming, and whether removal should require the explicit `--yes` after displaying the reversible trash plan. Implementation will start after this design is confirmed.
