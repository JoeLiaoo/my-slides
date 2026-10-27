# Design+Slides Spike 结果（issue #58 Phase 1）

**日期：** 2026-10-27  
**环境：** Windows 11，Node v24.22.1，Design+Slides 取自 `JoeLiaoo/lzj-skill` 的 `vendor/design-and-slides`（提交 `ea61050`），由 `MY_SLIDES_DESIGN_ROOT` 指定。  
**分支：** `feat/design-slides-spike`（my-slides 0.6.5）

## 做了什么

合成项目（3 个单元：`cover`、`market`、`team`，报告用测试夹具直接批准），按 README 的「Design+Slides 试点」一节逐步执行：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 初始化 | `init --presentation design` | `project.yaml` 写入 `presentation: "design"`；`init --force` 后仍保留 |
| 拒绝 Spec | `prepare spec --unit market` | 退出码 2，提示改用 `prepare slides` |
| 门禁 | 报告未批准时 `slides build` / `prepare slides` | 拒绝，列出未批准单元 |
| 同步 | `slides build --all` | 生成 `my-slides/design/deck/deck.json`，按章节写 `sections`，给缺页单元补占位页 |
| 写页 | 手写 `market.html`（KPI 卡片）和 `market_2.html`（内联 SVG 柱状图） | 再次同步后页序为 `cover, market, market_2, team` |
| 结构检查 | `slides check --all --strict` | Design `check_passed`，0 错误 0 警告 |
| 宿主 | 在引擎目录运行 `npm run dev -- --projects <项目>/my-slides/design` | `slides open` 报告宿主在运行；`/open/slides/deck` 302 跳转进编辑器 |
| 编辑器 | 用 playwright-core 打开 5173 截图 | 编辑器载入 4 页，缩略图与内容一致 |
| 模拟人工改动 | 通过宿主 `apply`（带 `ifMatch`）在封面后插入 `agenda` 页 | 发布成功；再次 `slides build` 后 `agenda` 留在封面后，列为 `unmapped_pages` |
| 渲染检查 | `slides check --all --browser` | Design `render_passed`，4 页，无警告 |
| 导出 | `export --output <dir>` | 383 KB 单文件 HTML；`file://` 离线打开正常，`#N` 可跳页；`.state/deliveries.json` 记录每单元报告哈希、审批人和各页哈希 |

截图核对过的页面：封面占位页、市场空间 KPI 页、内联 SVG 柱状图页、5173 编辑器总览。中文字体、配色、来源脚注均正常显示。

## 出过的问题（已修）

- 第一次实现按文本比较 `deck.json`，宿主写回的格式与我们不同（缩进、末尾换行），导致内容没变也重写文件，可能打断正在编辑的窗口。改为按 JSON 内容比较，相同则不写；已加测试。

## 发现的缺口（留给后续阶段）

1. **`next` / `status` 仍按 Spec 流程推荐下一步**（Phase 2）。design 项目里 Agent 应以 `prepare slides` 交接为准。
2. **同步直接写盘，不走宿主 `apply`。** 编辑器开着且有未保存改动时，`slides build` 改 `deck.json` 可能与人的改动冲突。Phase 3：宿主在线时通过 `apply` + `ifMatch` 发布，冲突时停下报告。
3. **交付差异比较还看旧哈希。** design 交付记录了各页哈希，但 `status` 的「自上次交付以来的变化」仍读 Spec/HTML 字段（Phase 3）。
4. **`export` 与 `slides check --browser` 需要宿主在运行**；`slides check` 不需要。已写进 README 和报错提示。
5. **没有自动视觉审阅。** Design 的 `render-check` 明确 `visualReview: "not-performed"`，旧的 `--screenshots` 证据目录在 design 模式下不可用。审阅靠人在 5173 上看。
6. **图表只能手写内联 SVG 或导入图片。** Design 没有 ECharts；Phase 3 需决定图表/图解的推荐写法（内联 SVG 模板、`import-asset` 导入渲染好的图）。
7. **Node 选择：** 使用 PATH 上第一个 `node`。本机 PATH 上排在前面的是另一个 Node 24，结果正常；Design `doctor` 会报告 `nodeSupported`，但 my-slides 没有单独指定 Node 的开关。
8. Edge 无头 `--screenshot` 打开编辑器页会一直挂起（长连接让虚拟时间跑不完）；截编辑器要用 playwright-core。只影响取证，不影响使用。

## 尚未验证（需要真人或其他设备）

- **在 5173 编辑器里真人手调页面**：本次只通过宿主的发布接口模拟了一次人工改动，没有人在浏览器里实际拖动或改字。需要 Joe 按 README 步骤试一次。
- macOS 上的同一流程。
- 真实投资项目（非合成数据）的出片质量对比。

## 结论

Design+Slides 可以承接「报告批准 → 写页 → 5173 审阅 → 离线导出」整条链路，接口足够 my-slides 薄封装。建议按计划进入 Phase 2（去掉 Spec、改写 `next`/`status`），并在 Phase 3 优先解决缺口 2（同步走 `apply`）。
