# my-slides × Design+Slides 重大迁移计划

**Status:** approved by Joe 2026-10-27 (Asia/Shanghai)  
**Repo:** JoeLiaoo/my-slides  
**Presentation engine:** Design+Slides (BaoCut slim) at JoeLiaoo/lzj-skill `vendor/design-and-slides` (local: `C:\Users\Admin\Desktop\lzj-skill\vendor\design-and-slides`)

## Product decision (interview)

| Decision | Choice |
|---|---|
| Pain | Agent blind-writes constrained HTML → ugly decks, many fix rounds |
| Operator model | Agent authors pages; Joe watches localhost:5173; small tweaks by hand; large changes → instruct Agent |
| Spec gate | **Remove** (no Spec prepare/approve/confirm) |
| Theme / charts / diagrams | **Migrate into Design+Slides** (not keep editorial-light + offline ECharts pipeline as primary) |
| Offline single-file HTML | Optional takeaway via Design `export html`; not a writing constraint |
| License | Personal use OK with BaoCut Community License; Design may be vendored/optional dep |
| Old issues | Close prior Spec/HTML-path issues (#45, #56, etc.); this migration supersedes |

Ideal flow:

```text
research materials / articles
  → Wiki (structure + provenance)
  → fixed-framework Report (unit/chapter based)
  → (report accepted)
  → Design+Slides deck (deck.json + slides/*.html)
  → Joe reviews on 5173; hand-tweak or Agent apply
  → optional: export offline HTML + record delivery metadata
```

## Architecture target

**my-slides = content & orchestration OS**  
**Design+Slides = presentation engine**

Keep:
- sources → wiki → report (fixed chapter framework)
- units / chapters management
- `next --json` style agent orchestration (updated for new stages)
- simplified human gate on **report** only (one confirm path; no Spec)
- optional delivery metadata (version, timestamp, unit hashes)

Remove / retire:
- Spec layer (commands, state, skill refs, tests)
- Agent-authored `slides/pages/<id>.html` fragment contract
- editorial-light shell assembly as primary deck builder
- primary offline ECharts/Lucide → SVG pipeline for slides (replace with Design-native / import-asset)
- dual-track “old HTML + Design” forever (migration window only)

## Design+Slides integration contract (known)

From `vendor/design-and-slides` README:
- Host: `npm run dev` → `127.0.0.1:5173`, projects folder via `--projects`
- Slides project: `deck.json` + `slides/*.html`
- Agent CLI: `doctor`, `list`, `init slides`, `open`, `apply`, `check`, `status`, `export --format html`
- `import-asset` for diagrams/images
- Files are source of truth; `apply` uses host `ifMatch`

my-slides should wrap these so Agent still gets few high-level commands (e.g. `prepare slides` / `slides open` / `slides check` / `export`) that shell out or document the Design CLI path.

**Vendoring recommendation:** add Design+Slides as `vendor/design-and-slides` (git subtree/submodule or documented clone from lzj-skill) OR document `MY_SLIDES_DESIGN_ROOT` env pointing at the install. Prefer vendoring a pinned copy or submodule so CI/docs are reproducible. Preserve BaoCut LICENSE + THIRD_PARTY_NOTICES; do not relicense as MIT.

## Progress

| Phase | State |
|---|---|
| 0 — plan in repo, superseded issues closed (#45, #56) | done |
| 1 — spike + thin CLI bridge behind `presentation: design` | done on `feat/design-slides-spike` (0.6.5); results in [spike-results.md](spike-results.md); real hand-edit on 5173 still needs Joe |
| 2 — remove Spec, rewrite `next` / `status` | done on `feat/design-slides-spike` (0.7.0), together with phase 3 |
| 3 — Design-only slides path | done (0.7.0): HTML pipeline removed; build/remove/restore/rename publish via host `apply` when it runs; check state recorded; delivery diffs use page hashes. Host-side `apply` success path verified only with mocks |
| 4 — docs + skill overhaul | next, awaiting approval |
| 5 — CI | pending (workflow still installs renderer/Playwright) |

## Implementation phases

### Phase 0 — Planning artifacts in-repo (this PR or first commit on branch)
- Add `docs/plans/design-slides-migration.md` (this plan)
- Open tracking issue (already created by coordinator)
- Close superseded issues with pointers

### Phase 1 — Spike (must land first, blocking)
Synthetic project under `examples/` or `tests/fixtures/`:
1. Minimal wiki + report (no Spec)
2. Command(s) that create/update a Design slides project from report units
3. Agent (or scripted) fills ≥2 pages via Design file format / apply
4. Document: start Design host with `--projects <path>`, open 5173, hand-edit works
5. `export html` produces openable file
6. Write `docs/plans/spike-results.md` with what broke and API gaps

**Done when:** a human can follow README steps to review the spike deck in Design host without using old `slides/pages` fragments.

### Phase 2 — Kill Spec + rewrite command/state machine
- Remove Spec from CLI, state (`.state`), skill, templates, AGENTS/README
- Update `next` / `status` / approval paths: report confirm remains; slides no longer require Spec
- Version bump: **minor** (breaking) per AGENTS.md + CHANGELOG Breaking Changes
- Tests: delete Spec-centric tests; add report→deck path tests

### Phase 3 — Slides path = Design only
- Replace `slides build` assembly with Design project sync + Design check/export
- Retire fragment parser / @scope shell / cache keyed on old HTML as primary
- Map `units.json` chapters ↔ deck sections/pages (stable IDs)
- Charts/diagrams: generate or import into Design assets; update skill to Design craft + diagram-design import (no auto bridge)
- Clean dead code: `assembly.py` old path, `rendering.py` chart path if unused, `slides_theme` editorial-light deck shell if unused, static-diagrams Spec-coupled refs

### Phase 4 — Docs + skill overhaul
- Rewrite README workflow (no Spec)
- Rewrite `skills/my-slides-workflow/` (+ sync templates)
- Document Design host + agent CLI; Windows PowerShell + macOS
- Migration note for existing projects with Spec/old HTML
- doctor: detect Design root / node / host readiness

### Phase 5 — CI
- Keep Python tests for wiki/report/orchestration
- Add or adjust jobs for Design dependency (Node) where needed
- Do not claim Mac/Windows device acceptance without evidence; mark pending if cloud-only

## PR slicing suggestion

1. **docs + plan + issue links** (small)
2. **Spike fixture + thin CLI bridge** (no full Spec deletion yet if needed for green CI—prefer feature flag `presentation: design` in project.yaml)
3. **Remove Spec + old slides pipeline** (breaking minor bump)
4. **Skill/README/doctor polish**

If one PR is preferred for momentum: still stage commits in that order.

## Explicit non-goals (v1)

- Relicensing BaoCut as MIT
- Interactive slide runtime / figure-spec DSL
- Replacing Wiki/report framework
- Requiring Joe to run Design for wiki/report-only work
- Closing unrelated healthy CI without replacement

## Success criteria (Joe)

- Same report → nicer slides with fewer blind-fix rounds
- Joe reviews on 5173; small edits by hand; large edits via Agent
- One coherent tool path (not two slide engines)
- Docs match reality

## Coordinator notes for coding agent

- Investigate freely; discard wrong hypotheses.
- Prefer deleting dead Spec/HTML paths over shims that preserve old behavior forever.
- When Design cannot be fully vendored in first PR, land spike + `MY_SLIDES_DESIGN_ROOT` + docs, then vendor.
- Do not invent BaoCut commercial rights; keep license files.
- Bump version + CHANGELOG per AGENTS.md on any breaking CLI/state change.
