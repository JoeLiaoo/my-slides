# Example index

Open when choosing a layout for a page. Examples live under `examples/` (or `src/my_slides/templates/examples/` in packaged installs). Each `page.html` is a complete Design page that passes `slides check --strict`; all data is fictional.

## 可用示例

| 版式 | 示例 | 适用内容 | 主要结构 |
| --- | --- | --- | --- |
| KPI 卡片 | `examples/investment-summary/01-cover-kpis/` | 封面、判断/收束 | 结论标题 + 3–5 个指标卡；支持理由与风险用不同强调色 |
| 哑铃对比 | `examples/competition/01-dumbbell/` | 对比、排序 | 内联 SVG：每个对象一行，两期数值连线 |
| 静态机制图 | `examples/technology/02-batching-static/` | 流程、因果、系统结构 | Design 形状 + 连线 + 钉住的文字，用户可直接改字 |

每个示例目录：

```text
examples/<category>/<id>/
├── README.md         # 用途、匹配的沟通问题、复用方法
├── data.json         # 虚构数据
├── wiki.md           # 假想的 wiki 索引片段
├── report-excerpt.md # 假想的报告段落（论证与边界）
├── page.html         # Design 页面
└── check-notes.md    # 期望通过的检查与视觉自检
```

复用时把 `page.html` 复制为 `slides/<单元 ID>.html`，把 `<section id>` 改成单元 ID，再按已批准报告替换内容。

## 按沟通问题选版式

没有现成示例的行，按「主要结构」一栏用 Design 的版式、表格或内联 SVG 自己搭；写法见 Design slides skill 与 `references/charts.md`。

| 沟通问题 | 目的 | 所需输入 | 边界 | 密度 | 推荐版面 |
| --- | --- | --- | --- | --- | --- |
| 一句话说「投 / 不投」 | 决策判断 | KPI 3–5 个 | 0–1 个情景 | 极低 | KPI 卡片（有示例） |
| 公司横评 / 排序 | 同业对比 | 3–6 家公司 + 2 期指标 | 同期数据 | 中 | 哑铃图（有示例）/ 并列柱 |
| 业务机理 / 推理流程 | 流程说明 | 3–6 步 | 单一链路、无性能数据 | 低 | 静态机制图（有示例） |
| 行业拐点 + 占比迁移 | 拐点解释 | 5–8 年序列 + 份额 | 同口径、同范围 | 中 | 折线 + 100% 堆叠条 |
| 投资判断及成立条件 | 证据链判断 | 判断 + 支撑证据 + 成立条件 | 无证据时不作判断 | 低 | 左判断、右条件的两栏 |
| 风险触发与待核实事项 | 风险描述 | 风险 + 触发条件 + 已知影响 | 不虚构概率或评分 | 低 | 三列表格 |
| 单位经济（LTV/CAC/回本） | 单点判断 | 12–24 个月 | 客单价稳定 | 中 | 折线 + 关键阈值线 |
| 财务情景 / 敏感性 | 风险量化 | 2 个变量 × 3 档 | 同时显示 | 中 | 情景矩阵表格 |
| 客户集中度 | 风险描述 | Top 5–10 客户 | 同期收入 | 低 | Top 表格 + 占比 |
| 团队 / 股权结构 | 关系说明 | 5–10 人 / 持股方 | 同快照日 | 低 | 列表 + 占比 |
| 退出 / 收益测算 | 情景对比 | 3 个退出情景 | 同一假设 | 中 | 哑铃 + 区间 |

同一版式连续最多两页；整套 deck 至少使用 `min(3, 总页数)` 种不同版式。
