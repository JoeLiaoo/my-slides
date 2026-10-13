# 检查备注

## 期望通过的结构检查

- 单元 ID：`unit-econ-payback`。
- 角色：`content`。
- `slide-notes`：含 payback_months、ltv_cac_ratio、threshold_payback_months、main_call、as_of。
- `mls-echarts-spec`：type = `line`；与 Spec 一致。
- `mls-lucide-spec`：含 `trending-up` 与 `wallet`；与 Spec 一致。

## 期望通过的视觉自检

- 一页一个结论（回本 8 个月 + LTV/CAC = 8.0）。
- 字号档位：标题 36 px / 副标 18 px / KPI 数值 28 px / 脚注 12 px。
- 数字带单位（元、8.0 倍）、阈值（12 个月）、来源。
- 关系类型 → 主视觉：时间序列 + 对比 → 折线 + KPI 卡片。
- 阅读顺序：标题 → 折线 → 0 轴 → 回本注释 → KPI → 脚注。
