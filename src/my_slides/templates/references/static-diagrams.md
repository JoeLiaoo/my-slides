# Static explanatory diagrams

Open only when the article describes a relationship that prose, a table, or a quantitative chart cannot show as clearly. The guidance is adapted from `cathrynlavery/diagram-design` at commit `550fd66edff058bc73056c3416b76d69cfe865ba` (MIT); none of its runtime, templates, CSS, or scripts are installed.

| Question | Preferred form | Diagram boundary |
| --- | --- | --- |
| How do actors exchange goods, money, or information? | Value-chain / value-flow diagram | Draw only documented direction and counterparties; distinguish movement from causation. Do not infer margins or market power from an arrow. |
| Which component depends on which? | Architecture / dependency diagram | Label the precise dependency and separate observed interfaces from conjecture. Do not imply performance or failure propagation without evidence. |
| What happens in what order, and what returns? | Process / feedback diagram | Use stages and an explicitly sourced feedback edge. A step order is not a duration or conversion rate. |

Keep a simple list as text, many-attribute comparisons as a table, and quantities/trends/compositions as charts (`references/charts.md`). If you cannot name the reader's question and the article paragraph or source behind each relationship, do not draw it. Changing what a diagram claims means updating the article and checking other targets.

For a chosen diagram:

1. List nodes, edges, labels, qualifiers, and the article paragraph or source for each. Mark uncertain or estimated relations in prose and the footnote. Avoid invented data, scores, arrow strengths, and decorative connectors.
2. Build it from Design primitives so the user can edit it on 5173: `<x-shape kind="rounded">` for nodes, a pinned `<p>` at the same position for each label, `<x-connector>` for arrows (`head="end"` only when direction is meaningful), `<x-icon>` sparingly. Format rules are in `<MY_SLIDES_DESIGN_ROOT>/skills/slides/references/format.md` §7.
3. Use inline `<svg>` only for shapes the primitives cannot express (curves, many small nodes). Keep labels outside the SVG where possible, since SVG text is not editable and ignores deck fonts; give the SVG `width`, `height`, `viewBox`, and an `aria-label` that states the relationship.
4. Keep every label at 28px or more on the 1920×1080 canvas. When the diagram needs more than about six nodes or long Chinese labels, split it across pages or show an ordered list instead of shrinking it. State what the illustration omits in the footnote.
5. Run `my-slides present --target slides` for Design `check --strict`, then use the engine's render check and look at the page on 5173 before handing it over.

`examples/technology/02-batching-static/` shows the article paragraph → Design shapes and connectors → boundary footnote path. Its arrows encode order only; its copy explicitly says there is no measured latency or throughput. For an investment value-flow diagram, reuse the same provenance discipline, not its technical subject matter.
