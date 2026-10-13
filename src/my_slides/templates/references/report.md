# Report reference

Open when preparing, reviewing, or revising a unit report (`reports/units/<id>.md`).

## Workflow per unit

1. `my-slides prepare report --unit <id>` → 写入 `my-slides/reports/units/<id>.md` 的交接材料（含单元 ID、大章节、角色、文件路径）。
2. 按 Wiki 页面撰写论证；保持章节顺序与 `project.yaml` 一致。
3. `my-slides validate report --unit <id>`：报告 ≥ 30 字符，本地 Markdown 链接全部解析。
4. `my-slides approve report --unit <id>` 仅提交待审申请；`review` 同时给出 APPROVE / REJECT 短语；用户明确批准后 `confirm --via chat`。
5. 所有单元确认后 `my-slides assemble` 生成 `reports/report.md`。

## Writing conventions

- 用普通 Markdown 链接引用 Wiki 或原始资料；保持单一报告单元一份 Markdown。
- 数字与单位写在相关句子附近；预测假设、证据缺口与日期用自然语言说明。
- 同一论点证据不足时显式列出待核实问题；不要为了填满章节编造数据。
- 不写 YAML frontmatter 或额外元数据；不引入新的分类体系。

## Format expectations

- 报告短于 30 字符会被 `validate` 拒绝（验证 `validate_unit_report`）。
- Markdown 链接失败（文件不存在）会一起报错。

## Boundaries

- 报告不引用未批准的下游材料；图表与图标的具体数值会进入 Spec「展示内容」。
- Spec 与 HTML 的具体排版不写在报告里；报告是论证与依据，Spec 才是页面决策。