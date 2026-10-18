# editorial-light theme profile

This is the authoring contract for the bundled theme. General evidence, layout, chart, and density rules remain in `example-index.md`, `spec.md`, `charts.md`, and `visual-rules.md`; this file defines only editorial-light's visual language.

## Use

Use editorial-light for investment committee materials, company and market analysis, diligence findings, and portfolio updates. It should read like a clear research memo projected on a screen: quiet paper surfaces, strong text hierarchy, restrained brand emphasis, and charts that support the claim.

The profile applies to new work. Choosing a theme does not change approved wording, page order, facts, figures, or the story. Use the project's configured `brand_color`; do not substitute a preset brand color.

## Visual tokens and typography

| Role | Rule |
| --- | --- |
| Canvas | Light surface from the bundled theme; preserve contrast and avoid decorative full-bleed gradients. |
| Primary text | `--mls-text` for titles, claims, table headings, and main values. |
| Supporting text | `--mls-muted` for explanations, labels, dates, and source notes. Keep it readable at presentation size. |
| Dividers | `--mls-divider` for thin separators; do not outline every paragraph as a card. |
| Brand | `--brand` / `--accent-blue` for one key emphasis, a conclusion marker, or a meaningful series. It comes from project configuration. |
| Chart series | `--mls-series-1` through `--mls-series-5`; keep series meaning consistent and never encode meaning by color alone. |
| Chinese type | Use the system CJK stack supplied by the shell. Do not load fonts from a network or override the shell font per page. |
| Numeric type | Use the existing tabular/monospace treatment only where it improves comparison; retain units and labels. |

Keep titles short enough to scan. Use body text for explanations, bold sparingly, and source/definition text at a readable footnote size. Do not shrink text to make a page fit; simplify or split the content.

## Information hierarchy

1. The title identifies the decision or reader question.
2. One primary visual carries the relationship: comparison, trend, sequence, or risk.
3. Explanatory text states evidence and conditions in reading order.
4. Source and scope notes sit near the supported claim, usually in the footer.
5. An author judgment appears only where the approved Spec marks a key page or chapter close.

Use the investment semantic components from `slides_theme/component-examples.md` when their inputs match. They do not require the same card layout on every page.

## Layout and pacing

- Alternate layouts according to the question: narrative opening, comparison, timeline, chart, table, case, or chapter close. Follow `example-index.md` limits for repeated layouts and deck variety.
- Use alignment and whitespace to show grouping. Prefer a table for several objects or dimensions; use a two-column comparison for two objects with a few parallel points.
- Use one restrained emphasis color for the main conclusion. Keep secondary facts neutral unless the data relationship needs a distinct series color.
- Leave open space between primary evidence and notes. Do not fill empty space with icons, badges, ornaments, or extra headings.
- Cover pages establish the subject and one-sentence purpose. Section transitions are brief. Closing pages state an implication supported by the preceding evidence.

## Charts, tables, and sources

- Use existing ECharts and semantic SVG rendering. Use series tokens consistently; keep axis labels, units, baselines, and source notes visible.
- Use a chart only when the data supports the visual comparison. Otherwise prefer a table or short evidence list.
- Never turn an unknown value into zero or imply completeness, ranking, probability, or causality without evidence.
- Keep labels readable at phone and desktop widths. Simplify, split, or change the chart form rather than shrinking dense labels.
- Normalize source notes as `机构或作者《标题》（日期）`; put definitions, estimates, and unverified status in the note once.

## Avoid and repair

| Failure | Repair |
| --- | --- |
| Every page is a row of rounded cards | Pick a form that matches the relationship: table, timeline, chart, comparison, or plain statement. |
| Brand color highlights every label | Keep it on the principal conclusion or one meaningful data series; use semantic neutral tokens elsewhere. |
| Icons decorate labels without adding meaning | Remove them; keep an icon only when it carries information. |
| Source notes or chart labels are tiny | Increase type size, reduce content, or split the page. |
| A fixed layout makes the page dense | Change layout or split the page while preserving approved content and traceability. |
| A beautiful cover hides a weak argument | Make the claim, evidence, and conditions visible in the body pages. |

## Scope and overrides

This profile does not override approved Spec content, evidence requirements, global `visual-rules.md`, project brand color, accessibility checks, or browser QA. Resolve a real conflict in the relevant global rule or code and review it; do not silently fork this profile in a page-local stylesheet.
