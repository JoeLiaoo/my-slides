# 检查备注

## 期望通过的结构检查

- 单元 ID：`fin-scenario`。
- 角色：`content`。
- `slide-notes`：含 base_case、reasonable_range、downside、upside、main_call、as_of。
- `mls-echarts-spec`：type = `heatmap`；与 Spec 一致。
- `mls-lucide-spec`：含 `grid-3x3` 与 `flame`；与 Spec 一致。

## 期望通过的视觉自检

- 一页一个结论（合理区间 + 基期）。
- 字号档位：标题 36 px / 副标 18 px / 顶部结论 22 px / 脚注 12 px。
- 数字带单位（IRR %）、区间（5–11 倍 / 20%–50%）、来源。
- 关系类型 → 主视觉：风险 / 情景 → 矩阵热力图。
- 阅读顺序：标题 → 顶部结论 → 热力图自左上至右下 → 基期高亮 → 脚注。
