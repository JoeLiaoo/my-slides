# Issue 28 — Phase 1: Unit management design

Status: design confirmed; Phase 1 implementation is in progress.

## Scope

This phase adds safe CLI operations for the ordered unit inventory in `my-slides/units.json`:

- `my-slides units add <id> --chapter <chapter> [--after <id>] [--role content]`
- `my-slides units remove <id> [--yes] [--json]`
- `my-slides units move <id> [--after <id> | --before <id>] [--chapter <chapter>]`
- `my-slides units rename <old-id> <new-id>`
- `my-slides units restore <trash-id>`
- `my-slides units trash list [--json]`

It also reports orphaned per-unit artifacts and makes CLI assembly use the same manifest validation as other project commands. The low-level `assemble_report()` remains a pure file/link assembler; command entry points validate the manifest and current approvals before writing a formal report.

Approval history, diff/reject/withdraw/revoke, chapter-management commands, delivery/export, cleanup, and browser-check policy remain separate later phases in Issue 28.

## Invariants

1. Every operation loads and validates the complete manifest against `project.yaml` before planning changes, then validates the proposed manifest before writing anything.
2. Unit IDs stay unique and regex-safe; exactly one cover remains at array index zero; units remain grouped in configured chapter order.
3. An omitted `--after`/`--before` inserts or moves a content unit after the last unit in its requested chapter, or before the first later configured chapter when that chapter is empty. `--after` and `--before` name an existing unit in the requested chapter and are mutually exclusive. `--before` can place a unit first in a chapter. Commands reject ambiguous or invalid insertion points rather than silently reordering unrelated chapters.
4. A new unit receives visible TODO skeletons for its report, Spec, and HTML fragment. A Spec may describe multiple slides. Skeletons are not treated as validated or approved content.
5. Same-chapter reordering preserves report and Spec approvals, but invalidates the whole deck and its browser checks because slide order changed. A cross-chapter move requests report reconfirmation with the review context limited to `章节：甲 → 乙，内容未变`; Spec approval remains current while the approved report and dependency closure are unchanged. HTML is rebuilt and the deck is rechecked.
6. Rename preserves report and Spec approvals when the operation only changes identity metadata, paths, and exact local links to the renamed unit. It records the identity migration in state. If a rewritten report or Spec has a substantive content change, that artifact's approval becomes stale. HTML and browser checks are invalidated in all cases.
7. Removal is preview-only by default. Human-readable and `--json` previews list all files to move (report, Spec, page, preview, state, dependency declaration), current approvals, dependencies, inbound unit dependencies, and local Markdown links. Removal of the cover or a unit with inbound dependencies/references is blocked until those references are resolved. `--yes` moves the unit into `.state/trash/<timestamp>-<id>/`, saving the exact manifest entry, original position, original paths, and hashes. `units trash list` enumerates recoverable removals. `units restore <trash-id>` restores to the original chapter and position only when paths are free and the resulting manifest is valid; old approvals are re-evaluated against current content fingerprints and dependency closure.
8. Structural changes invalidate aggregate outputs without deleting them. Keep the last `reports/report.md` and `slides/index.html` available as prior output, mark deck build/check state stale, and make `next` recommend reassembly/rebuild before completion. Record the manifest identity used for the last formal deck so a changed unit order is detectable. Cached HTML remains content-addressed and can be reused only if ordinary cache-key checks pass.
9. Orphan detection covers per-unit files in `reports/units`, `specs/units`, `slides/pages`, `slides/previews`, `.state/units`, and `reports/units/*.depends-on.json` whose IDs are absent from the manifest. It does not treat cache, snapshots, or trash as active unit artifacts.

## Transaction and recovery model

Each mutation follows the same sequence:

1. Read the manifest, config, known unit files, sidecar dependencies, and target paths; build a human-readable operation plan and validate the proposed manifest before mutation.
2. For removal, print the complete affected-artifact, approval, and reference plan. Without `--yes`, do not mutate project files. `--json` returns the same plan for an Agent to explain to the user. Agents may run `--yes` only after obtaining user consent when the unit has an existing approval; every successful removal prints its restore command.
3. For remove/restore/rename, record each completed file move or rewrite so caught errors can be rolled back. For removal, write a trash manifest containing the original entry, position, paths, and hashes.
4. Atomically replace `units.json` after the file operations. If an operation reports an error before commit, restore moved files and state snapshots. Preserve aggregate outputs at their normal paths; invalidation is represented in state and recomputed against the new manifest.

The trash manifest maps every saved unit path to its original project-relative path and SHA-256. The restore command refuses collisions; it never overwrites user files. Operations must remain confined to the `my-slides/` workspace after path resolution.

This protects against ordinary command failures and publishes `units.json` atomically. It is not a filesystem-wide transaction: a process kill or power loss mid-operation can leave an orphan or incomplete move. `doctor` and `units list` report orphaned artifacts; inspect the trash manifest before manual recovery after an interrupted command.

## Operation details

### Add

Validate ID, chapter, role, and placement. Create report, Spec, and page skeletons under their canonical unit paths and insert the unit at the calculated position. Adding a second cover is rejected; the initial cover remains `cover` unless a later explicit rename operation is requested.

### Remove

Show a read-only plan by default, including every artifact path, approval state, outgoing and inbound dependency declarations, and inbound local Markdown links. Support the same plan with `--json`. Block removal of the cover or a target with unresolved inbound references/dependencies. With `--yes`, move artifacts and exact manifest metadata into `.state/trash/<timestamp>-<id>/`; print `my-slides units restore <trash-id>` after success. Trash is excluded from scanning and delivery. Cleanup is deferred to Issue 28 Phase 5.

### Move

Move the entry within its chapter or to a specified chapter while preserving manifest validity. `--after <id>` places it after that unit, `--before <id>` places it before that unit (including the first position of the chapter), and omitting both appends it to the target chapter so an empty chapter can receive a unit. Same-chapter moves preserve report/Spec approvals and invalidate the assembled deck and browser checks. Cross-chapter moves preserve the Spec approval when its bound report fingerprint is unchanged, and create a report reconfirmation request with context `章节：<旧章节> → <新章节>，内容未变`. HTML is rebuilt and checks rerun; dependent approvals are invalidated only if their dependency closure changes.

### Rename

Require a free destination ID. Migrate the report, Spec, page, preview, state, and dependency sidecar; update identity-only headings, the Spec `页面 ID`, page root `data-unit-id`, and exact unit IDs in dependency sidecars. Rewrite local Markdown links inside `my-slides/` that target the old unit's canonical report/Spec/page paths. Never rewrite original project sources; if one links to the unit, refuse the rename and list that file. Do not globally replace arbitrary prose containing the old ID. Preserve approvals when only identity metadata and canonical links change; otherwise invalidate the affected approval. Record old/new IDs and migration time. HTML/check state is always invalidated.

## Test plan for implementation PR

- Add places units within a chapter and before the next chapter; rejects duplicate IDs, unknown chapters, invalid roles, and a second cover.
- Remove preview is read-only, human/JSON output lists affected files, approval state, and inbound references; `--yes` moves to trash and prints restore instructions; restore preserves original position and revalidates approvals; collisions are refused; trash list works.
- Same-chapter move preserves report/Spec approvals and invalidates deck/checks; cross-chapter move queues only report reconfirmation with the context message and preserves unchanged Spec approval.
- Rename migrates files and declared dependencies, rewrites only supported metadata/links, preserves approvals for mechanical identity-only changes, invalidates substantive changes, and rebuilds under the new ID.
- Orphan reporting finds each supported orphan path and ignores cache/trash.
- Invalid manifest edits never partially change the manifest or lose files; CLI `assemble` rejects a manifest/order mismatch just like `doctor`, `next`, and `slides check`.
- Keep existing report/Spec/HTML dependency and browser-check regression tests passing.

## Confirmed decisions

- Reapproval follows substantive changes to reviewed content. Cross-chapter movement asks the user to reconfirm the report with a context-only message, while an unchanged report-bound Spec approval remains valid.
- Mechanical renames preserve existing report/Spec approvals; substantive changes invalidate the affected approval.
- Removal previews by default and uses `--yes` to move into recoverable trash. Agents may execute it, but must first obtain user consent when the target has an approval. The skill documents this requirement.
- Preview supports `--json`; restore/list commands, original-position recovery, complete impact reporting, and the specified trash path are in scope.
- Trash cleanup remains in Issue 28 Phase 5 and is out of scope here.
