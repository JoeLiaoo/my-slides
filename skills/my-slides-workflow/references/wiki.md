# Wiki reference

Open when preparing Wiki material, indexing new sources, or answering research questions.

## Layout

```
my-slides/
├── wiki/
│   ├── README.md       # 维护约定（创建时由 init 生成）
│   ├── index.md        # 按报告章节组织的导航
│   ├── log.md          # 追加的维护记录
│   └── *.md            # 主题页面（按需创建）
```

## Conventions

- 使用自然语言与普通 Markdown；不写 frontmatter、标签或来源 ID。
- 引用使用相对 Markdown 链接；引用项目根目录资料时按页面所在层级计算相对路径。
- 索引按 `project.yaml` 章节顺序组织；同一主题可出现在多个章节下。
- 数字口径、预测假设、信息日期、不确定性写到正文相关段落，不另开字段。
- 资料移除或改名后用 `validate wiki` 检查断链；与正文冲突的差异用一句话指出，不强行调和。

## Operating steps

1. `my-slides sources scan` 获取待整理 / 已移除资料。
2. `my-slides prepare wiki` 生成 `my-slides/work/wiki.md`；按交接材料把新资料整合进现有主题页。
3. 更新 `index.md` 与 `log.md`；运行 `my-slides validate wiki`，修复断链。
4. 完成后 `my-slides sources mark-ingested`，下次扫描以新指纹为基础。
5. 用户提研究问题时运行 `my-slides prepare wiki --question "..."`，按交接材料从 index 定位相关页面后综合回答。

## Boundaries

- Wiki 扫描与组织是 CLI 职责；具体内容（结论、摘要、研究笔记）由 Agent 撰写。
- 原始项目资料保持只读；不要复制到 `my-slides/wiki/` 再编辑。
- 准备阶段的 `prepare wiki` 不会修改 Wiki 本身；Agent 在阅读交接材料后写入 `wiki/*.md`。