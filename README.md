# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

项目以 `my-slides/units.json` 中的单元组织：每个单元对应一份报告、一份 Spec、一页 HTML，支持按单元审阅与增量构建。

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

## 先装这些

| 用途 | 需要先有 | 然后运行 |
| --- | --- | --- |
| 使用命令 | Python 3.11 或更新版本，以及安装工具 [uv](https://docs.astral.sh/uv/) | 下面的 `uv tool install` |
| 图表和图标 | Node.js 和 npm | `my-slides renderer install`（装好 ECharts 6.1.0 和 Lucide 1.52.0） |
| 手机和电脑屏幕检查 | 安装命令里带上 `[browser]` | `my-slides browser install`（下载 Playwright Chromium） |

只做资料整理、报告和结构检查时，有 Python 和 uv 即可。没装 Node.js 时，带图表或图标的页面生成不了。没装浏览器时，`slides check` 仍可做结构检查，加上 `--browser` 才会测屏幕显示。装完可运行 `my-slides doctor` 查看这三项是否就绪。

## 开始使用

安装后先运行 `my-slides help`。它会向 Agent 说明工具职责、项目初始化、Wiki → 报告 → Spec → Slides 的完整流程、逐单元命令和需要用户审阅的节点；在项目目录外也能运行。`my-slides --help` 显示命令列表，`my-slides <命令> --help` 显示参数，`my-slides help --json` 输出可供 Agent 读取的 JSON。

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

### 版本

用 `my-slides --version`（或 `-V`）查看本机安装的版本号。可编辑安装（`uv tool install --editable …`）在 `git pull` 后会随仓库 `pyproject.toml` 的 `[project].version` 更新。**合并进 `main` 的 PR 必须在同一 PR 内把 `[project].version` 的 patch +1**（见 [`AGENTS.md`](./AGENTS.md)）；勿依赖 CI。

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
