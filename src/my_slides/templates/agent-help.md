# My Slides：给首次使用的 Agent

0.8.0 新项目默认是薄壳：`my-slides init --project <项目>` 只创建 `my-slides/project.json`。在配置中选择 beautiful 与/或 slides，准备非空 `article.md`，运行 `my-slides present --json` 获取分目标交接和确定性检查。CLI 不自动写正文或页面；未完成返回非零。Design 结构检查通过后仍需渲染、事实核对和用户在 5173 审阅。具体见仓库 `docs/remake-contract.md` 和安装的 workflow skill。

下文仅适用于用 `my-slides init --legacy` 显式建立的 0.7 单元项目；新项目不运行旧审批链。

My Slides 是投资项目目录中的本地工作流工具。你（Codex、Claude Code 或其他 Agent）阅读项目资料，维护 Markdown Wiki，按小章节撰写投资报告；报告经用户批准后，在 Design+Slides 里写演示页面，用户在 `127.0.0.1:5173` 上审阅、手调，最后导出离线 HTML。CLI 负责初始化、提供阶段交接材料、检查产物、记录用户审批、同步 Design deck 和记录交付；CLI 本身不会替你撰写内容。

开始前

1. 在项目目录运行 `my-slides init --legacy`；若当前目录不是项目目录，各项目命令加 `--project <项目目录>`。
2. 运行 `my-slides agent install` 安装项目级 Agent 指引，阅读 `my-slides/project.yaml`、`my-slides/units.json` 和安装的工作流指引。
3. 运行 `my-slides doctor`、`my-slides units list`、`my-slides status --json`、`my-slides next --json`，确认项目结构、单元状态和下一步。`next` 的 `actor: human` 表示必须交给用户本人。缺少 `units.json` 的旧项目需要重新初始化。
4. 写页阶段需要 Design+Slides 引擎：环境变量 `MY_SLIDES_DESIGN_ROOT` 指向已 `npm install` 并 `npm run build` 的 design-and-slides 目录。`my-slides doctor` 的 `design.ready` 为真才算就绪。

按阶段执行（以下命令均在项目目录中运行）

1. Wiki：`my-slides sources scan` → `my-slides prepare wiki` → 阅读来源 Markdown 并更新 `my-slides/wiki/` → `my-slides validate wiki` → `my-slides sources mark-ingested`。原始资料保持只读。Wiki 使用普通 Markdown 和链接；从 `wiki/README.md`、`wiki/index.md` 开始，不添加复杂标签。
2. 报告：`my-slides units list` 找到稳定单元 ID；对每个单元运行 `my-slides prepare report --unit <id>`，按交接材料撰写 `my-slides/reports/units/<id>.md`，再运行 `my-slides validate report --unit <id>`。`my-slides approve report --unit <id>` 只会提交待审申请，不会批准。接着运行 `my-slides review report --unit <id>`，把输出贴到对话里并停下来。`review` 同时给出 `APPROVE` 与 `REJECT` 两条短语。用户明确批准这个小章节或这一章之后，才能运行 `my-slides confirm report --via chat --phrase "APPROVE ..." --user-reply "<原话>"`。用户也可以驳回：`reject report --unit <id> --reason "..." --via chat --phrase "REJECT REPORT <id> <sha12>" --user-reply "..."` 清除待审申请并记录原因；只接受 `REJECT` 短语，已批准内容不会被作废。Agent 想取消自己的申请可运行 `withdraw report --unit <id>`。撤回已批准报告用 `my-slides revoke report --unit <id> --via chat`：先不带 `--phrase` 拿到 `REVOKE` 短语与已批准版本摘要，用户在对话中明确同意后再带 `--phrase` 和 `--user-reply` 执行。全部单元批准后运行 `my-slides assemble`。
3. 证据数字：`my-slides prepare evidence-research`，把可复核的公开硬数字写进 `my-slides/research/numbers.md`（编号、值、单位、期间、出处），再运行 `my-slides validate evidence-research`。页面里的图表数字只能取自这份清单。
4. 写页：`my-slides prepare slides --unit <id>` 生成写页交接（`my-slides/work/slides/<id>.md`）。页面格式严格按 Design+Slides 自带的 slides skill（`<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md`）：1920×1080，每个文件恰好一个 `<section>`，样式全部写在 `style` 属性里。文件写在 `my-slides/design/deck/slides/`，单元第一页叫 `<id>.html`，后续页叫 `<id>_2.html`、`<id>_3.html`。内容只来自已批准报告，缺的写成 `[待补：…]`。写完运行 `my-slides slides build --unit <id>` 同步页序与分节，再运行 `my-slides slides check --all`（加 `--strict` 时警告也算失败）。
5. 审阅：运行 `my-slides slides open`，把审阅链接和启动宿主的命令交给用户，然后停下。用户在 5173 上看：小改自己手调，大改口述给你。改页前一定重新读目标文件，在用户改过的内容上改，不要凭记忆整页重写。宿主运行时 `slides build` 通过宿主发布；如果报冲突，说明用户在编辑器里改过同一文件，停下来告诉用户。
6. 交付：用户满意后，在宿主运行时运行 `my-slides export [--output <目录>]`。它检查全部单元的报告批准和页面是否齐全，通过则导出 `<项目名>-v<序号>-<日期>.html`，并在 `.state/deliveries.json` 记录交付时间、版本号、各单元报告与页面的 SHA-256。`status --json` 的 `delivery` 字段显示最近一次交付与之后变化的单元。

每个单元 ID 是一个小章节：一份报告，以及 Design deck 里的一页或多页。大章节来自 `project.yaml` 的 `chapters`。只改页面版式不需要重新审批；改页面上的结论或数字要先改报告、重新审批。用 `--unit <id>` 处理单个小章节；批量处理受影响单元用 `--changed`，全部单元用 `--all`；同一大章节一起提交用 `approve --chapter`。默认在对话里审批：不能把「继续」「看起来不错」当成批准，也不能扩大用户点名的范围。`reject` 与 `revoke` 沿用同一套门：`approval_mode: terminal` 时 Agent 不得运行；任何模式下都不得借助伪终端、`script`、`expect`、tmux `send-keys` 或管道代填。

单元清单变更使用 `my-slides units add/move/rename/remove`，不要手工改 `units.json`。删除默认只预览影响，确认后用 `--yes` 把报告和该单元的 Design 页面一起移入 `.state/trash/`，并保留输出的恢复命令。删除曾获报告批准的单元前，Agent 必须先征得用户明确同意；有未解决依赖或链接时命令会阻止删除。`my-slides units trash list` 查看回收区，`my-slides units restore <trash-id>` 恢复原位置和页序；`units rename` 会一起改页面文件名和 `deck.json` 引用。章节调整需用户重新确认报告。清单变化后重新运行 `slides build --all` 和 `slides check --all`。

大章节调整使用 `my-slides chapters list/add/rename/remove/move`，一次同步 `project.yaml`、`units.json`、`wiki/index.md`；重命名不影响报告批准。删除仍被小章节引用的大章节会被命令拒绝。

其他：`my-slides next --all` 汇总全部待办并按 Agent / 用户分组。`my-slides agent doctor` 检查已安装的工作流指引，不会覆盖修改过的文件；`my-slides agent install` 只补装缺失文件。`my-slides clean` 默认只预览 30 天前的 `work/` 交接与 Wiki 快照；确认清单后再加 `--yes` 删除。`my-slides --help` 查看命令列表；`my-slides <命令> --help` 查看参数；`my-slides help --json` 获取机器可读的本指南；`my-slides --version` 查看版本。
