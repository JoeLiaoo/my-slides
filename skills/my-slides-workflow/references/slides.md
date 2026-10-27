# Slides reference

Open when writing or revising Design pages from `article.md`, or when the user asks for changes after reviewing on 5173.

## 分工与工作流

- Design+Slides 自带的 `<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md` 负责页面格式、写法、`apply`、`render-check` 和导出；本参考只补投资汇报的内容与表达规则。
- 阅读 `project.json` 中的正文路径和 slides 输出路径。默认 deck 为 `my-slides/design/deck`，宿主 projects 根是其父目录。页面从正文取材，可删减或重组，但不能无依据增加结论或数字。
- Agent 按 Design skill 创作并更新页面。在线修改前重读目标文件，经引擎 `apply` 发布；连接失败、超时或 409 冲突时保留现场，不能直写盘覆盖。
- 运行 `my-slides present --target slides --json`。`succeeded` 只表示 Design `check deck --strict` 通过，`content_sync` 始终是 `unknown`。另由引擎运行渲染检查，请用户在 5173 审阅。可选离线导出由引擎执行。

## 写页前先想清楚（每页）

| 问题 | 要写到什么程度 |
| --- | --- |
| 读者问题 | 读者打开这页最想知道的一件事 |
| 唯一结论 | 读完带走的一句话，写成页面标题 |
| 关系类型 | 时间序列、结构构成、对比、因果流程或风险情景，决定主视觉 |
| 主视觉 | 明确图形、元素和字段 |
| 阅读顺序 | 2–4 个停留点，例如标题 → 高亮行 → 脚注 |
| 形式理由 | 为什么这种图形比其他形式更清楚 |

## 内容规则

- 页面上的结论、数字、引语、人名应能在正文或其可核对来源中找到；缺的写成 `[待补：…]`，不编造。正文变化后核对受影响页面；用户在页面改动实质内容时，回写正文和其他目标，或明确记录该目标的差异。
- 一页一个结论，标题就是结论句。超过两个并列结论就拆页。作者判断只放在有明确证据的关键页；访谈原话是证据，不能替作者下判断。
- 数字必须保留单位、期间、口径与来源；同一数字避免在多页机械重复。没有可靠数字时用表格、清单或结构图组织定性证据。
- 来源脚注写机构或作者、标题、日期，并说明估计或未核验状态。讲稿按 Design skill 放置，说明重点和不能推出的结论。
- 同一种版式连续不超过两页；参考 `references/example-index.md`。图表、图片和静态图解见 `charts.md` 与 `static-diagrams.md`。

## 尊重用户手改

用户会在 5173 上直接改页面。只改用户点名的页和地方；重新读当前文件，在已有内容上修改。根据 Design skill 处理编辑器标注。结构检查不等于渲染、事实核对或视觉认可。
