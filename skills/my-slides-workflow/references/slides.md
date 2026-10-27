# Slides reference

Open when writing or revising Design pages from an approved report, or when the user asks for changes after reviewing on 5173.

## 分工

- **页面格式与 Design 写法**以 Design+Slides 自带的 slides skill 为准：`<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md` 及其 `references/format.md`、`references/design.md`。`prepare slides` 的交接材料会给出它在本机的绝对路径。不要凭记忆写标签或样式：1920×1080 画布，每页恰好一个 `<section>`，样式全部写在 `style` 属性里，不能用 `class`、`<style>`、`<script>`。
- **本参考只补投资汇报特有的规则**：内容从哪来、一页讲什么、数字和来源怎么写、和 my-slides 命令怎么配合。

## 工作流

1. 报告批准、`assemble` 完成、`research/numbers.md` 通过 `validate evidence-research` 之后，运行 `my-slides prepare slides --unit <id>`。交接材料写入 `my-slides/work/slides/<id>.md`，列出已批准报告、页面文件名和规则。
2. 在 `my-slides/design/deck/slides/` 写页面：单元的第一页是 `<id>.html`，后续页是 `<id>_2.html`、`<id>_3.html` ……；`<section id>` 与文件名一致。`slides build` 生成的占位页含「[待写：」，`next` 会一直提醒直到写完。
3. `my-slides slides build --unit <id>`（或 `--all`）：按 `units.json` 同步 `deck.json` 的页序、分节和封面，给缺页单元补占位页，不覆盖已有页面。不要手改 `deck.json` 的 `order` / `sections` / `cover`。
4. `my-slides slides check --all`：Design 结构检查，并核对每个单元至少有一页。加 `--strict` 时警告也算失败；宿主运行时加 `--browser` 再做一次真实渲染检查。
5. 自查 `references/visual-rules.md` 后运行 `my-slides slides open`，把审阅链接交给用户，停下来等用户看。
6. 用户满意后，在宿主运行时运行 `my-slides export [--output DIR]` 导出离线 HTML 并记录交付。

## 写页前先想清楚（每页）

动笔前在心里（或交接文件的草稿里）回答这六个问题；答不上来就回到报告，不要先画：

| 问题 | 要写到什么程度 |
| --- | --- |
| 读者问题 | 读者打开这页最想知道的一件事，例如「客户集中在哪些行业」 |
| 唯一结论 | 读完带走的一句话，能被一两个数字或一句对比概括；写成页面标题 |
| 关系类型 | 时间序列 / 结构构成 / 对比 / 因果流程 / 风险情景，决定主视觉（见 `references/charts.md`） |
| 主视觉 | 具体到元素和字段：「哑铃图：每家公司一行，空心点 2022、实心点 2024」 |
| 阅读顺序 | 2–4 个停留点，例如「标题 → 高亮行 → 其余行 → 脚注」 |
| 为什么是这个形式 | 一句取舍，例如「哑铃比并列柱更直接显示两期差值」 |

## 内容规则

- **唯一来源是已批准报告**。页面上的数字、引语、人名都要能在报告或 `research/numbers.md` 里找到；缺的写成 `[待补：…]` 并在交付时列出，不要编。改动结论或数字等于改报告：先改报告并重新走审批。
- **一页一个结论**，标题就是结论句。超过两个并列结论就拆页；封面单元一页，内容单元建议不超过八页。
- **作者判断框**（「我们的判断 / 对投资的含义」）只放在章节收束页或用户点名的关键页；嘉宾或访谈原话只作证据，不能替作者下判断。
- **数字**：只用 `research/numbers.md` 已登记的值；同一个数字编号在整套 deck 只在最能支撑结论的一页出现。没有合适数字的页用表格、清单或结构图组织定性证据。
- **来源脚注**：每张内容页一行，格式 `机构或作者《标题》（日期）`；估计、未核验状态和口径在脚注里一次说清，正文不重复限定词。
- **讲稿**写在最后的 `<aside>` 里：先讲什么、重点数字、不能推出的结论。
- **版式节奏**：同一种版式连续不超过两页；整套 deck 至少 `min(3, 总页数)` 种版式。参考 `references/example-index.md`。

## 改页：尊重用户的手改

- 用户会在 5173 上直接改页面。动手前**重新读目标文件**，在现有内容上改，不要凭记忆整页重写；用户拖动过的元素变成 `position:absolute`，照样保留。
- 只改用户点名的页和地方。用户在编辑器里做的标注会以 `<baocut-slide-annotations>` 附在消息里，按 Design slides skill 的「按幻灯片标注修改」处理。
- 宿主运行时，`slides build` 与 `units remove/restore/rename` 通过宿主的 `apply` 发布，并带上读取时的版本。如果命令报冲突，说明用户在编辑器里改过同一文件：停下来告诉用户，不要强行覆盖。
- 不属于任何单元的页面（例如用户手加的议程页）保留在原位置；`slides build` 会把它们列为 `unmapped_pages`，不会删除。

## 图表、图片与图解

- 图表：Design 没有图表库，写成页面里的内联 `<svg>`（见 `references/charts.md` 和 `examples/competition/01-dumbbell/`）。
- 流程、结构、价值流：优先用 Design 的 `<x-shape>`、`<x-connector>`、`<x-icon>` 和钉住的文字，用户可以直接改字（见 `references/static-diagrams.md`）。
- 图片或已渲染好的图：在引擎根目录运行 `npm run slides:import-asset -- <deck 目录> <文件>`，把返回的 `/_blob/<id>` 写进 `<img src>`。网址、相对路径都不能用。

## 边界

- `slides build` / `prepare slides` 只处理报告已获当前有效批准的单元；撤回报告批准后，该单元要重新走报告审批，页面再按新报告修改。
- Design 不做自动视觉审阅；`slides check` 通过只说明格式合法。好不好看、读者能否看懂，由用户在 5173 上判断。
- `export` 和 `slides check --browser` 需要宿主在运行；`slides check` 不需要。
