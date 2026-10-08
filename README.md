# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

**当前仅支持 v2 单元格式**（`my-slides/units.json`）。旧版章节格式与章节迁移（`migrate`）已移除；请重新 `init`。

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
my-slides slides check --unit <id>          # 结构检查（单元集合/顺序、封面）
my-slides slides check --unit <id> --browser  # 另需 Playwright Chromium
```

也可用 `--changed` 或 `--all`。默认的 `slides check` 只做结构检查；加 `--browser` 才跑桌面/手机视口测量。

无 `units.json` 时 CLI 会拒绝执行；请重新 `my-slides init`。

### 最小冒烟（命令骨架）

在任意空投资项目目录：

```text
my-slides init --project <项目根>
my-slides prepare wiki && …整理 wiki… && my-slides validate wiki
my-slides sources mark-ingested
my-slides prepare report --unit <id> && …撰写… && validate/approve report --unit <id>
my-slides assemble
my-slides prepare spec --unit <id> && …撰写… && validate/approve spec --unit <id>
my-slides prepare slides --unit <id> && …写单页 HTML…
my-slides slides build --all
my-slides slides check --all
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
