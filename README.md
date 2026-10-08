# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

第一版本地工作流已打通，后续按路线图完善 Wiki、Reports 和 Slides。工具由本地 CLI 与当前 Agent 协同工作：Agent 负责分析与内容生成，工具负责项目文件组织、来源追溯、版本和审阅状态、图表图标渲染及 Slides 检查。当前以 Markdown 为资料输入，文档转换由用户预先完成。

## 目标工作流

```text
项目 Markdown 资料
        ↓
项目 Wiki 与来源追溯
        ↓
完整投资报告（用户审阅）
        ↓
分章 Presentation Spec（用户审阅）
        ↓
分章 HTML Slides → 合并为整套离线演示文稿
```

预期能力包括：

- 为每个投资项目建立独立的 Markdown Wiki，以普通专题页面和页面链接积累知识，并按报告章节组织索引；来源、判断与待核实事项按需写入正文，不强制标签分类。
- 增量发现新增、修改和删除的资料，标出受影响的 Wiki 页面和报告章节。
- 按可配置的 PE／IC 章节模板生成有证据、有来源映射的完整投资报告。
- 将报告按章节整理为分页 Spec，逐页记录结论、证据、来源、布局和图表数据。
- 使用 `bluedusk/html-slides` 作为页面生成指导，结合 ECharts 和 Lucide 生成统一主题的 HTML Slides，并进行页面合并和浏览器检查。
- 在报告与 Spec 阶段保留用户审阅节点；内容变更后更新下游状态，同时保留历史版本。

计划中的 Slides 默认采用 16:9 专业 IC 风格，以红色作为品牌色。最终演示文稿预期为单个可离线打开的 HTML 文件。

## Roadmap

1. **实现第一版本**：建立 CLI 与项目目录基础，打通从 Markdown 资料到 Wiki、投资报告、Spec 和 HTML Slides 的最小端到端流程；支持基本来源追溯及报告、Spec 审阅。
2. **完善 Wiki 功能**：强化增量更新、页面关联、来源版本、冲突识别、待核实事项和资料变化影响分析。
3. **完善 Reports 功能**：完善 PE／IC 章节模板、证据与计算依据、Wiki 引用映射、按章节修订及版本管理。
4. **完成 Slides 功能**：完善分章生成与合并、统一主题、ECharts 图表、Lucide 图标、离线输出及桌面和手机浏览器质量检查。

## 开始使用

在仓库根目录安装开发版 CLI：

```powershell
uv tool install --editable ".[browser]" --link-mode copy --cache-dir .uv-cache
my-slides renderer install
my-slides browser install
my-slides init --project "C:\Projects\某投资项目"
my-slides agent install --project "C:\Projects\某投资项目"
my-slides doctor --project "C:\Projects\某投资项目"
my-slides sources scan --project "C:\Projects\某投资项目"
my-slides prepare wiki --project "C:\Projects\某投资项目"
```

`my-slides agent install` 会在项目 `.agents/skills/` 与 `.claude/skills/` 安装工作流技能，并保留已有同名文件。DeepSeek harness 可读取同一技能说明或每个 `prepare` 命令生成的交接材料。Agent 按项目内 Wiki 约定和索引整理资料；完成后运行 `my-slides sources mark-ingested`，再用 `prepare report`、`prepare spec` 和 `prepare slides` 依次获取下一阶段的交接材料。报告与 Spec 经用户审阅后，运行对应的 `approve` 命令。

包含图表或图标的项目需先运行 `my-slides renderer install`；使用 `slides check --browser` 前运行 `my-slides browser install`。随后把 HTML 章节片段放入项目 my-slides/slides/chapters/，运行 `my-slides slides build` 合并为 my-slides/slides/index.html。渲染依赖固定为 ECharts 6.1.0 与 lucide-static 1.52.0，并安装在用户本机的工具运行目录中；最终 HTML 将图表和图标内联为 SVG，附带第三方许可与来源信息。

## 当前状态

CLI 已提供项目初始化、按报告章节建立和补齐 Wiki 索引、Markdown 变化扫描、Agent 交接材料与项目级工作流技能、Wiki／报告／Spec 检查、报告与 Spec 审批版本联动、图表与图标本地 SVG 渲染、章节 HTML 合并，以及 Chromium 桌面和手机视口检查。自动回归覆盖六章合成项目的端到端流程；生成内容仍由当前 Agent 撰写，真实项目的页面质量需要逐页审阅。

单元化改造（issue #1）已落地步骤 1：`units.json` 读取与校验、报告单元组装、`my-slides units list`，以及 `my-slides migrate --to-units --dry-run` 只读迁移预检。现有项目仍默认走 v1 章节路径；存在 `my-slides/units.json` 时识别为 v2。

运行基础回归测试：

```powershell
$env:PYTHONPATH = "src"
$env:MY_SLIDES_RENDERER_HOME = Join-Path $env:LOCALAPPDATA "MySlides\renderer"
python -m unittest discover -s tests -v
```

实施计划见 [`docs/plans/local-investment-wiki-slides.md`](docs/plans/local-investment-wiki-slides.md)，报告章节来自 [`docs/templates/投资报告章节.md`](docs/templates/投资报告章节.md)。
