# 检查备注

## 期望通过的结构检查

- 单元 ID：`competition-dumbbell`。
- 角色：`content`。
- `slide-notes`：含 metric、highlight_company、main_call、as_of。
- `mls-echarts-spec`：type = `dumbbell`；与 Spec 一致。
- `mls-lucide-spec`：含 `minus` 与 `plus`；与 Spec 一致。

## 期望通过的视觉自检

- 一页一个结论（aurora 增量最大）。
- 字号档位：标题 36 px / 副标 18 px / 行内 Δpp 14 px / 脚注 12 px。
- 数字带单位（pp）、日期范围、来源。
- 关系类型 → 主视觉：对比 → 哑铃图，非并列柱。
- 阅读顺序：标题 → 哑铃自上而下 → Aurora 高亮行 → 脚注。
