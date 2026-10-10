# My Slides

[![CI](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml)

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

项目以 `my-slides/units.json` 中的单元组织：每个单元对应一份报告、一份 Spec、一页 HTML，支持按单元审阅与增量构建。

## 目标工作流

```text
项目 Markdown 资料
        ↓
项目 Wiki 与来源追溯
        ↓
报告单元（reports/units/<id>.md）→ 提交申请 → 用户在终端逐单元确认
        ↓
Spec 单元（specs/units/<id>.md）→ 提交申请 → 用户在终端逐单元确认
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

克隆仓库，在仓库目录中安装命令：

```bash
git clone https://github.com/JoeLiaoo/my-slides.git
cd my-slides
uv tool install --editable ".[browser]" --link-mode copy --cache-dir .uv-cache
my-slides help
```

`my-slides help` 会向 Agent 说明工具职责、项目初始化、Wiki → 报告 → Spec → Slides 的完整流程、逐单元命令和需要用户审阅的节点；在项目目录外也能运行。`my-slides --help` 显示命令列表，`my-slides <命令> --help` 显示参数，`my-slides help --json` 输出可供 Agent 读取的 JSON。

这是可编辑安装；更新工具时保留该目录并运行 `git pull`。然后为投资项目初始化工作区（将占位路径换成实际路径）：

```text
my-slides renderer install
my-slides browser install
my-slides init --project "<投资项目目录>"
my-slides agent install --project "<投资项目目录>"
my-slides doctor --project "<投资项目目录>"
my-slides next --project "<投资项目目录>" --json
```

按单元推进：

```text
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>       # Agent 提交待审申请，不会批准
my-slides confirm report --unit <id>       # 用户本人在交互终端执行
my-slides assemble
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>         # Agent 提交待审申请
my-slides confirm spec --unit <id>         # 用户本人在交互终端执行
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id>          # 结构检查（单元集合/顺序、封面）
my-slides slides check --unit <id> --browser  # 另需 Playwright Chromium
```

也可用 `--changed` 或 `--all`。默认的 `slides check` 只做结构检查；加 `--browser` 才跑桌面/手机视口测量。

`my-slides next --json` 返回下一步命令、目标单元、原因和执行者（`agent` 或 `human`）。Agent 遇到 `actor: human` 必须停下，请用户自行审阅并执行 `confirm`。`approve` 只记录文件内容与依赖的待审版本；`confirm` 不提供 `--json` 或批量确认，要求在交互终端输入审阅者姓名与针对当前 SHA-256 的确认文字。状态文件记录姓名、本机账户与批准时间。申请后若文件或依赖变化，确认会拒绝，必须重新提交。完成报告确认后运行 `assemble`。

交接材料使用固定路径 `my-slides/work/wiki.md`、`my-slides/work/wiki-question.md` 和 `my-slides/work/<report|spec|slides>/<id>.md`；再次 `prepare` 会更新同一路径。`status --json` 的 `approvals.<kind>.current` 按选定单元计算，仅在其批准版本仍有效且有审阅者姓名和本机账户时为真；另列出待确认、需重审及旧版无审阅者记录的单元。旧批准必须重新确认才能继续组装报告或构建 Slides。`slides.current` 表示构建有效，`slides.checked_current` 表示浏览器检查有效。

交互终端与自填姓名只能减少误操作，**不能阻止 Agent 有意绕过**。常见 Agent 可通过伪终端、输入自动化或直接改写本地状态伪造确认；用户应亲自核对 `status --json` 里的审批人和时间。若需要可验证的强制人审，必须使用独立身份与权限的外部审批系统。

无 `units.json` 时 CLI 会拒绝执行；请重新 `my-slides init`。

### 版本

用 `my-slides --version`（或 `-V`）查看版本。开发 checkout 会同时显示短提交号；工作区有改动时会标记“有未提交修改”。正式安装包没有 Git 信息时仍只显示版本号。`my-slides help --json` 也会返回 `version`、`commit` 和 `dirty`。

每个 PR 都要按影响选择版本级别，在 [`CHANGELOG.md`](./CHANGELOG.md) 添加对应版本条目。兼容新增、修复和文档升 patch；不兼容的命令或状态变化升 minor 并把 patch 归零，更新日志必须有“不兼容变更”分类；major 版本需要维护者批准。只改 `.github/`、`tests/` 或 `scripts/` 的 PR 可以不升版本。PR CI 会阻止漏升、跳号、版本级别与不兼容标记不符或漏写更新日志。测试通过后，CI 会给 `main` 上尚未打过的版本自动创建并推送 `vX.Y.Z` tag。规则见 [`docs/versioning.md`](docs/versioning.md) 与 [`AGENTS.md`](./AGENTS.md)。

### 最小冒烟（命令骨架）

在任意空投资项目目录：

```text
my-slides init --project <项目根>
my-slides prepare wiki && …整理 wiki… && my-slides validate wiki
my-slides sources mark-ingested
my-slides prepare report --unit <id> && …撰写… && my-slides validate report --unit <id>
my-slides approve report --unit <id>  # 提交申请；用户另行 confirm report
my-slides confirm report --unit <id>  # 用户本人执行
my-slides assemble
my-slides prepare spec --unit <id> && …撰写… && my-slides validate spec --unit <id>
my-slides approve spec --unit <id>    # 提交申请；用户另行 confirm spec
my-slides confirm spec --unit <id>    # 用户本人执行
my-slides prepare slides --unit <id> && …写单页 HTML…
my-slides slides build --all
my-slides slides check --all
```

## 测试

PR、推送到 `main` 和手动触发时，[GitHub Actions 工作流](.github/workflows/ci.yml)会在 Ubuntu 上运行完整回归（Python 3.11、Node 22、渲染器和 Chromium）。本地也可运行：

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

## 许可

本项目采用 [MIT 许可证](LICENSE)。内置的上游幻灯片主题保留其[原始许可证](src/my_slides/slides_theme/upstream/LICENSE)。
