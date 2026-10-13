# example：投资摘要封面 KPI

> 类别：投资摘要
> 目的：一句话说「投 / 不投」，附 3–5 个 KPI。
> 关系类型：对比 + 风险。
> 密度：极低（一页结论 + 卡片）。
> 用途：整套 deck 的封面之后、第一段投资摘要；也用于临时一页式快速判断。

## 数据

`data.json` 是虚构 KPI，单位、口径、来源都明确标注；不要把里面的数字搬到真实项目。

```text
project            : Aurora Logistics
unit_id            : cover-kpis
chapter            : 投资概要
role               : cover
purpose            : 一句话说投 / 不投
inputs             : 3–5 个 KPI（估值、增速、回本、集中度、风险）
bounds             : 数据日期 2024-12-31；货币 CNY；不考虑跨境税务
density            : 极低
layout             : 单段标题 + KPI 卡片网格
```

## 文件清单

```text
data.json         虚构 KPI 数据
wiki.md           假想 wiki 索引片段
report-excerpt.md 报告「投资摘要」段落摘录
spec.md           Spec 完整示例（含 6 个布局意图子项）
page.html         单页 slide HTML
check-notes.md    期望通过的结构 / 视觉检查
```

## 与索引的对应

对应 `references/example-index.md` 中的行：

- 沟通问题：「一句话说投 / 不投」 → 极低密度、决策判断。

## 复现

```bash
cp -r example/investment-summary/01-cover-kpis /tmp/aurora-cover
cd /tmp/aurora-cover
# 把 data.json 换成真实数字即可；其余结构（spec / page）按 spec.md 写。
```
