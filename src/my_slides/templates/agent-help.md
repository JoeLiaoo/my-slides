# My Slides：给首次使用的 Agent

My Slides 是研究正文到 beautiful 长文和/或 Design+Slides 幻灯的薄壳。CLI 只有 `init`、`present`、`help` 和 `--version`；不会生成正文、HTML 或幻灯内容。阅读安装的 my-slides-workflow skill 和仓库 `docs/remake-contract.md`。

1. 保持项目原始材料只读。运行 `my-slides init --project <项目目录>`，它只创建 `my-slides/project.json`；已有配置不会覆盖。编辑 `present`，启用 `beautiful`、`slides` 或两者。
2. 用现有成文，或由 Agent 完成非空 UTF-8 `article.md`。正文保留来源、日期、数字口径和待补项。所有配置路径相对项目根。
3. 运行 `my-slides present --project <项目目录> --json`。读取每个目标的状态与 `next`；`--target beautiful|slides` 只处理所选目标。未完成时退出非零，失败不覆盖已有产物。
4. beautiful 的 `pending_agent` 是制作和核对交接，即使 HTML 已存在也一样。slides 需要 `MY_SLIDES_DESIGN_ROOT` 指向已安装、构建的 Design+Slides；Agent 先读引擎的 slides skill，制作页面后再运行 `present`。slides 的 `succeeded` 只代表 `check deck --strict` 通过。
5. Agent 对照正文核对每个目标的内容。`content_sync: unknown` 不代表已同步。另由引擎做渲染检查，请用户在 5173 审阅；视觉和事实认可不能由 CLI 自动宣称。在线改页经引擎 `apply`，冲突或断线时不直写覆盖。

从旧项目迁移时，把正文整理进 `article.md` 并添加 `project.json`；旧审批、Wiki 和 Report 可保留为历史，不能自动批准新正文。旧命令已删除；需要操作旧流程时使用对应旧版本。
