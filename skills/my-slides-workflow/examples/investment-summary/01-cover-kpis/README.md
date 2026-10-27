# example：投资摘要封面 KPI

> 类别：投资摘要
> 目的：一句话说「投 / 不投」，附 3–5 个 KPI。
> 关系类型：对比 + 风险。
> 密度：极低（一页结论 + 卡片）。
> 用途：整套 deck 的封面；也用于临时一页式快速判断。

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
layout             : 标题写结论 + 五列 KPI 卡片（支持理由蓝色、风险红色）
```

## 文件清单

```text
data.json         虚构 KPI 数据
wiki.md           假想 wiki 索引片段
report-excerpt.md 报告「投资摘要」段落摘录
page.html         Design 页面（1920×1080，单个 <section>，样式全部写在 style 属性）
check-notes.md    期望通过的检查与视觉自检
```

## 与索引的对应

对应 `references/example-index.md` 中的「一句话说投 / 不投」。

## 复用

把 `page.html` 复制为 deck 的 `slides/<单元 ID>.html`，把 `<section id>` 改成同一个 ID，再按已批准报告替换文字和数字。卡片数量可在 3–5 之间增减，`grid-template-columns` 跟着改。
