# My Slides：给首次使用的 Agent

My Slides 是投资项目目录中的本地工作流工具。你（Codex、Claude Code 或其他 Agent）阅读项目资料，维护 Markdown Wiki，撰写逐页报告和 Presentation Spec，再生成离线 HTML Slides。CLI 负责初始化、提供阶段交接材料、检查产物、记录用户审批和合并页面；CLI 本身不会替你撰写内容。

开始前

1. 在项目目录运行 `my-slides init`；若当前目录不是项目目录，各项目命令加 `--project <项目目录>`。
2. 运行 `my-slides agent install` 安装项目级 Agent 指引，阅读 `my-slides/project.yaml`、`my-slides/units.json` 和安装的工作流指引。
3. 运行 `my-slides doctor`、`my-slides units list`、`my-slides status --json`、`my-slides next --json`，确认项目结构、单元状态和下一步。`next` 的 `actor: human` 表示必须交给用户本人执行。缺少 `units.json` 的旧项目需要重新初始化。

按阶段执行（以下命令均在项目目录中运行）

1. Wiki：`my-slides sources scan` → `my-slides prepare wiki` → 阅读来源 Markdown 并更新 `my-slides/wiki/` → `my-slides validate wiki` → `my-slides sources mark-ingested`。原始资料保持只读。Wiki 使用普通 Markdown 和链接；从 `wiki/README.md`、`wiki/index.md` 开始，不添加复杂标签。
2. 报告：`my-slides units list` 找到稳定单元 ID；对每个单元运行 `my-slides prepare report --unit <id>`，按交接材料撰写 `my-slides/reports/units/<id>.md`，再运行 `my-slides validate report --unit <id>`。运行 `my-slides approve report --unit <id>` 只会提交待审申请，不会批准；请用户审阅后在自己的交互终端运行 `my-slides confirm report --unit <id>`。Agent 不得运行 `confirm`。需要整份报告时运行 `my-slides assemble`。
3. Presentation Spec：运行 `my-slides prepare spec --unit <id>`，撰写 `my-slides/specs/units/<id>.md`，运行 `my-slides validate spec --unit <id>`。`my-slides approve spec --unit <id>` 只提交待审申请；用户本人审阅并运行 `my-slides confirm spec --unit <id>`。
4. Slides：只根据已批准的 Spec 运行 `my-slides prepare slides --unit <id>`，生成 `my-slides/slides/pages/<id>.html`，运行 `my-slides slides build --unit <id>` 和 `my-slides slides check --unit <id>`。需要桌面与手机视口检查时加 `--browser`。

每个单元 ID 对应一份报告、一份 Spec、一页 HTML。修改单个页面时用 `--unit <id>`；批量处理受影响单元用 `--changed`，全部单元用 `--all`。这些选择参数适用于逐单元的 prepare、validate、approve、slides build/check 命令；`confirm` 始终逐单元由用户执行。Agent 不得借助伪终端、`script`、`expect`、tmux `send-keys`、管道或读取 `.state/` 来代填确认。用 `my-slides next --json` 获取下一条建议及原因。交接材料写入固定的 `my-slides/work/<阶段>/<id>.md`，再次 prepare 会覆盖同一文件。

单元清单变更使用 `my-slides units add/move/rename/remove`，不要手工改 `units.json`。删除默认只预览影响，确认后使用 `--yes` 移入 `.state/trash/`，并保留输出的恢复命令。删除曾有报告或 Spec 批准记录的单元前，Agent 必须先征得用户明确同意；有未解决依赖或链接时命令会阻止删除。可用 `my-slides units trash list` 查看回收区，用 `my-slides units restore <trash-id>` 恢复原位置。章节调整需用户重新确认报告；未变的 Spec 批准保留。单元清单或身份变化后重建整套 Slides 并重新检查。

生成 Slides 前可运行 `my-slides renderer install` 安装本地 ECharts/Lucide 渲染依赖；使用 `--browser` 前可运行 `my-slides browser install`。`slides check` 不带 `--browser` 时只做结构检查。

其他入口：`my-slides --help` 查看命令列表；`my-slides <命令> --help` 查看参数；`my-slides help --json` 获取机器可读的本指南；`my-slides --version` 查看版本。
