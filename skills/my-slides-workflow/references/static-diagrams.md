# Static explanatory diagrams

Open only when an approved Spec calls for an explanatory relationship that prose, a table, or a quantitative chart cannot show as clearly. The adapted guidance is based on `cathrynlavery/diagram-design` at commit `550fd66edff058bc73056c3416b76d69cfe865ba` (MIT). No upstream runtime, templates, CSS, or script is installed. Re-evaluate the source and license before adopting further assets. `frontend-slides` contributes only the existing practice of choosing layout for the content; its template packs are not loaded.

| Question | Preferred form | Diagram boundary |
| --- | --- | --- |
| How do actors exchange goods, money, or information? | Value-chain / value-flow diagram | Draw only documented direction and counterparties; distinguish movement from causation. Do not infer margins or market power from an arrow. |
| Which component depends on which? | Architecture / dependency diagram | Label the precise dependency and separate observed interfaces from conjecture. Do not imply performance or failure propagation without evidence. |
| What happens in what order, and what returns? | Process / feedback diagram | Use stages and an explicitly sourced feedback edge. A step order is not a duration or conversion rate. |

Keep a simple list as text, many-attribute comparisons as a table, and quantities/trends/compositions as the existing ECharts + metric path. If the Spec cannot name the reader's question and each relationship's approved paragraph or source, do not draw it. Return to the existing report/Spec review for semantic changes; layout-only edits may use the existing rebuild and QA path.

For a chosen diagram:

1. List nodes, edges, labels, qualifiers, and source/paragraph locations in the approved Spec. Mark uncertain or estimated relations in prose and the footnote. Avoid invented data, scores, arrow strengths, and decorative connectors.
2. Author a self-contained inline `<svg viewBox="…" role="img" aria-labelledby="…">` with `<title id="…">` and `<desc id="…">`; include text that explains the relationship outside the image. Use a local `<defs><marker>` only when arrow direction is meaningful. The build namespaces SVG IDs, `url(#…)`, fragment hrefs, and ARIA ID references per unit/page/diagram. Keep every ID unique **within** the SVG.
3. Use the current project's editorial-light color tokens and three-level type scale; keep CSS scoped to the slide. Do not copy an upstream full HTML page, global CSS, JS, or external font. A project brand choice belongs in its own project configuration, never in a shared installed style guide.
4. For long Chinese labels or mobile viewports, split complex relationships into more pages or show an ordered text alternative; never make a huge diagram unreadably small. State what the illustration omits. Check the built HTML with `slides check --all --browser --screenshots`, inspect three viewport images and record visual review. Missing browser/render dependencies cannot count as completed QA.

The synthetic batching mechanism under `examples/technology/02-batching-static/` demonstrates the approved Spec → inline SVG → text alternative → notes path. Its arrows encode order only; its copy explicitly says there is no measured latency or throughput. No network access is needed to build or open it. For an investment value-flow example, use the same provenance discipline, not its technical subject matter.
