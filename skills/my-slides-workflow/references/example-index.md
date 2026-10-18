# Example index

Open when choosing a layout, a chart, or a Spec sketch. `prepare slides` reads this index to surface the 1–2 most relevant example paths for the current Spec — it does not dump the full library into context. Examples live under `examples/` (or `src/my_slides/templates/examples/` in packaged installs).

## 用法

1. 在 Spec「布局意图」六个子项里写下当前页的：读者问题、唯一结论、关系类型、主视觉、阅读顺序、形式取舍。
2. 在下面表格中找到最贴近的「目的 → 输入 → 边界 → 密度 → 版面」组合，挑出 1–2 个 example 路径。
3. `my-slides prepare slides` 会按同一张索引自动把对应路径与摘要贴进交接材料，避免你从头搜。
4. 真正动手前，复制 `examples/<category>/<id>/` 到本地 fixture，再按你的数据替换。

## 可用版式目录

每页 Spec 都要声明一个“内容类型”和一个版式。以下版式均对应仓库中可重建的 `html-slides` 示例；若一页不适合任何数字图表，可用表格、清单或静态结构图表达，版式仍选与信息关系匹配的一类。

| Spec 版式名 | 示例来源 | 适用内容类型 | 主要结构 |
| --- | --- | --- | --- |
| KPI卡片 | `examples/investment-summary/01-cover-kpis/` | 判断/收束、案例 | 标题 + 3–5 个指标卡 |
| 语义组件并列与分区 | `examples/investment-components/01-semantic-components/` | 对比、判断、风险 | 证据比较 / 判断与条件 / 风险与触发点 |
| 哑铃对比 | `examples/competition/01-dumbbell/` | 对比 | 两期 / 多对象的同指标差异 |
| 100%堆叠趋势 | `examples/market-trend/01-pivot-share-shift/` | 演进/时间线、趋势/图表 | 时间轴 + 份额迁移 |
| 漏斗流程 | `examples/technology/01-funnel/` | 演进/时间线、案例 | 阶段转化 + 瓶颈 |
| 静态机制图 | `examples/technology/02-batching-static/` | 演进/时间线、案例 | 有序步骤、因果关系或系统结构 |
| 敏感性热图 | `examples/financial-scenario/01-sensitivity/` | 清单/矩阵、趋势/图表 | 两变量情景矩阵 |
| 单位经济折线 | `examples/unit-economics/01-payback/` | 趋势/图表、判断/收束 | 单位经济指标 + 回本时间序列 |

同一版式连续最多两页；整套 deck 至少使用 `min(3, 总页数)` 种不同版式。完整 deck 达到三页后至少三种；更短的 deck 每页尽量不同。

## 默认类别

每个类别下面至少有 1 个可重建的最小例子（Wiki/sources → report 摘录 → Spec → HTML → check 备注）。所有数字都是**虚构的**，可在 `data.json` 里看到。

| 类别 | 目录 | 常见关系类型 | 典型结论形态 |
| --- | --- | --- | --- |
| 投资摘要 | `examples/investment-summary/` | 对比 / 风险 | 一句话判断 + 关键 KPI 表 |
| 市场 / 需求趋势 | `examples/market-trend/` | 时间序列 + 结构构成 | 拐点 + 占比变化 |
| 竞争比较 | `examples/competition/` | 对比 | 多列对比 / 矩阵气泡 |
| 技术机制 | `examples/technology/` | 因果 / 流程 | 漏斗 / 流程图 |
| 商业化与单位经济 | `examples/unit-economics/` | 时间序列 + 对比 | LTV、CAC、回本周期 |
| 财务情景与风险 | `examples/financial-scenario/` | 风险 / 情景 | 区间条 / 矩阵 |
| 投资语义组件 | `examples/investment-components/` | 对比 / 判断 / 风险 | 证据比较 / 判断与条件 / 风险触发点 |

## 按沟通问题检索

下面这张表让 `prepare slides` 与人工按相同逻辑挑出最相关示例。每行写明：purpose（页的目的）、inputs（所需输入）、bounds（边界）、density（密度）、layout（推荐版面）。匹配按从左到右的优先级打分；命中数最高的两条 example 进入交接。

| 沟通问题 | purpose | inputs | bounds | density | layout |
| --- | --- | --- | --- | --- | --- |
| 一句话说「投 / 不投」 | 决策判断 | KPI 3–5 个 | 0–1 个情景 | 极低 | 单段标题 + KPI 卡片 |
| 行业拐点 + 占比迁移 | 拐点解释 | 5–8 年序列 + 份额 | 同口径、同范围 | 中 | 折线 + 堆叠条并列 |
| 公司横评 / 排序 | 同业对比 | 3–6 家公司 + 2 指标 | 同期数据 | 中 | 哑铃 / 并列柱 |
| 投资判断及成立条件 | 证据链判断 | 判断 + 支撑证据 + 成立条件 | 无证据时不作判断 | 低 | `examples/investment-components/01-semantic-components/` |
| 风险触发与待核实事项 | 风险描述 | 风险 + 触发条件 + 已知影响 | 不虚构概率、评分或损失 | 低 | `examples/investment-components/01-semantic-components/` |
| 业务机理 | 流程说明 | 3–6 步 | 单一链路 | 中 | 漏斗 / 流程图 |
| 推理服务批处理 | 步骤和取舍 | 队列、批次、执行 | 定性机制、无性能数据 | 低 | 静态五步图；`examples/technology/02-batching-static` |
| 单位经济（LTV/CAC/回本） | 单点判断 | 12–24 个月 | 客单价稳定 | 中 | 折线 + 关键阈值 |
| 财务情景 / 敏感性 | 风险量化 | 2 个变量 × 3 档 | 同时显示 | 中 | 矩阵气泡 / 区间条 |
| 客户集中度 | 风险描述 | Top 5–10 客户 | 同期收入 | 低 | Top 表格 + 占比 |
| 政策 / 驱动力 | 因素拆解 | 3–5 个驱动 | 累计可加 | 中 | 横向条 + 同比 |
| 团队 / 股权结构 | 关系说明 | 5–10 人 / 持股方 | 同快照日 | 低 | 列表 + 占比 |
| 退出 / 收益测算 | 情景对比 | 3 个退出情景 | 同一假设 | 中 | 哑铃 + 区间 |

## 已知匹配规则

`prepare slides` 按以下启发式挑出最相关的示例（用于在没有 Spec 草稿的早期阶段也能给出参考）：

1. 看 Spec 的「目的 / 唯一结论」关键词：是否含「拐点」「横评」「机理」「敏感性」「集中度」。
2. 看 Spec 的「关系类型」是否落在上表的关系类型列。
3. 看 Spec「展示内容」里声明的图表类型是否能在 example 中复现。

命中 1–2 个即把对应 example 路径与一句话摘要写入交接；命中 0 时退到默认推荐：`market-trend/01-industry-pivot`（最通用）。`prepare slides` 不会把整个 example 库放进交接材料，避免污染上下文。

## fixture 复现规则

每个 example 目录都遵循：

```text
examples/<category>/<id>/
├── README.md         # 用途、目标问题、匹配本索引里的哪一行
├── data.json         # 虚构数据；不可用真实公司 / 真实数据
├── wiki.md           # 假想的 wiki 索引片段（说明资料来源）
├── report-excerpt.md # 假想的报告段落（论证与边界）
├── spec.md           # 一份完整 Spec，覆盖六个布局意图子项
├── page.html         # 完整 slide HTML（含 slide-notes）
└── check-notes.md    # 期望通过的结构检查 / 视觉自检清单
```

把整个目录 `cp -r` 到任何空白项目里就能复现；Spec 验证、HTML 结构检查都基于 `data.json` 重算，不依赖网络。
