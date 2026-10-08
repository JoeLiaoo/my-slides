# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

本仓库当前处于规划阶段。工具将由本地 CLI 与当前 Agent 协同工作：Agent 负责分析与内容生成，工具负责项目文件组织、来源追溯、版本和审阅状态、图表图标渲染及 Slides 检查。第一版以 Markdown 为资料输入，文档转换由用户预先完成。

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

- 为每个投资项目建立独立的 Markdown Wiki，索引资料、记录事实与判断、管理来源及待核实事项。
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

## 当前状态

仓库目前包含产品方案，尚未开始 CLI 和生成流水线的实现。详细设计见 [`docs/plans/local-investment-wiki-slides.md`](docs/plans/local-investment-wiki-slides.md)。
