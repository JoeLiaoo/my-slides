# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

**当前仅支持 v2 单元格式**（`my-slides/units.json`）。旧版章节格式已移除；请先迁移或重新 `init`。

## 目标工作流

```text
项目 Markdown 资料
        ↓
项目 Wiki 与来源追溯
        ↓
报告单元（reports/units/<id>.md）→ 用户按单元审阅
        ↓
Spec 单元（specs/units/<id>.md）→ 用户按单元审阅
        ↓
单页 HTML（slides/pages/<id>.html）→ 增量合并为整套离线演示文稿
```

每个单元有稳定 ID，对应一份报告、一份 Spec、一页 HTML。改单元 A 时只处理 A 及真正依赖它的部分。

## 开始使用

```powershell
uv tool install --editable ".[browser]" --link-mode copy --cache-dir .uv-cache
my-slides renderer install
my-slides browser install
my-slides init --project "C:\Projects\某投资项目"
my-slides agent install --project "C:\Projects\某投资项目"
my-slides doctor --project "C:\Projects\某投资项目"
```

按单元推进：

```text
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>
my-slides assemble
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id> --browser
```

也可用 `--changed` 或 `--all`。

## 从旧项目迁移

若目录仍是旧章节布局（无 `units.json`），日常命令会拒绝执行。请用本版本的迁移命令：

```text
my-slides migrate --to-units --dry-run --project <路径>
my-slides migrate --to-units --project <路径>
my-slides migrate --rollback --project <路径>
```

## 测试

本仓库**没有 GitHub Actions**。请在本地跑：

```bash
# 快速（缺渲染器/浏览器时相关用例会 skip）
./scripts/run-quick-tests.sh

# 完整门禁：安装渲染器 + Chromium，缺依赖则失败
./scripts/run-full-tests.sh
```

Windows PowerShell 快速跑：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

说明见 [`docs/testing.md`](docs/testing.md)。实施计划见 [`docs/plans/local-investment-wiki-slides.md`](docs/plans/local-investment-wiki-slides.md)。
