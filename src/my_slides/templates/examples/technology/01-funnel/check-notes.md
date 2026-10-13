# 检查备注

## 期望通过的结构检查

- 单元 ID：`tech-funnel`。
- 角色：`content`。
- `slide-notes`：含 bottleneck、target_2024、main_call、as_of。
- `mls-echarts-spec`：type = `funnel`；与 Spec 一致。
- `mls-lucide-spec`：含 `arrow-down` 与 `target`；与 Spec 一致。

## 期望通过的视觉自检

- 一页一个结论（瓶颈 + 改进目标）。
- 字号档位：标题 36 px / 副标 18 px / 顶部结论句 24 px / 脚注 12 px。
- 数字带单位（%）、基数（1000）、来源。
- 关系类型 → 主视觉：因果 / 流程 → 漏斗图，非饼图。
- 阅读顺序：标题 → 顶部结论句 → 漏斗自上而下 → 「激活 → 首次付费」段高亮 → 脚注。
