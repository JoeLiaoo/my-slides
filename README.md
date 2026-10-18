# My Slides

[![CI](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml)

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

项目以 `my-slides/units.json` 中的小章节（单元）组织：每个小章节属于一个大章节，对应一份报告、一份 Spec 和若干页 HTML。审批、修改和增量构建都以小章节为单位。

## 当前能力（#38 已合入）

issue [#38](https://github.com/JoeLiaoo/my-slides/issues/38) 已合入并关闭。读者可直接用到：

| 能力 | 怎么用 |
| --- | --- |
| 截图与视觉 QA | `slides check --browser --screenshots` 保存三视口逐页 PNG、contact sheet 与带指纹的 `measurements.json`；看图后用 `slides visual-review` 记录观察。手机视口图表内过小文字为 `warnings`（不挡交付）；桌面字号与 SVG 标签越界仍为硬错误。 |
| 页内 metric 绑定 | Spec 可选 `metric-spec`；HTML / KPI / 讲稿用 `{{metric:id.field}}`，单系列图用 `metricRefs`。详见 skill `references/charts.md`。 |
| 图表语义校验 | 拒绝重复类别/系列；时间顺序、构成比例、瀑布总计、零基线等规则在构建/检查中生效；图表可写 `summary` 供 SVG 可读名称。 |
| 主题 token 与可访问性 | CSS 与离线 SVG 共用语义色 token；浏览器检查含文字对比度、图表说明，以及按钮 / 键盘 / 触摸导航。 |
| 静态解释图试点 | 示例 `skills/my-slides-workflow/examples/technology/02-batching-static/`：静态 SVG + 窄屏文字顺序 + 文字对照；多视口实测已写在 `pilot-evaluation.md`。 |

**未做、不承诺：** 受控 figure-spec、交互运行时、真人盲测读者理解。需要时再单独开 issue；普通报告继续用文字、表格、现有图表和（必要时）手工静态 SVG。

Spec 校验还会检查每页内容类型与示例库版式、整套 deck 的版式节奏与种类下限，以及数字 ID 是否跨页重复。每个数字只在最能支撑结论的一页出现；无合适数字时用表格或结构图。作者判断框仅用于章节收束页或标注的关键页。review 与 `slides visual-review` 按 `references/visual-rules.md` 检查版式多样性和单页信息密度。

Issue #45 中“每页都必须有判断框和数字”的要求已被当前按需呈现规则取代；标准来源脚注与证据清单要求保留。详见 [Issue #45 处理说明](./docs/design/issue-45-resolution.md)。

当前唯一内置主题是 `editorial-light`。主题 profile 约定字级、语义色、图表、脚注与版式节奏；`prepare spec` 和 `prepare slides` 会指出该 profile。主题只影响新产物的呈现，不改写已批准内容或 Spec。见 `skills/my-slides-workflow/references/editorial-light-theme.md`。


## 目标工作流

```text
项目 Markdown 资料
        ↓
项目 Wiki 与来源追溯
        ↓
报告小章节（reports/units/<id>.md）→ 提交申请 → 在对话中按小章节或整章确认
        ↓
Spec 小章节（specs/units/<id>.md）→ 提交申请 → 在对话中按小章节或整章确认
        ↓
小章节 HTML（slides/pages/<id>.html，可含多页）→ 增量合并为整套离线演示文稿
```

每个小章节有稳定 ID。例如「行业分析」下面可以有「需求分析」「竞争分析」，各自写一页或多页。改某个小章节时只处理它以及真正依赖它的部分；只改某一页的版式、不改 Spec 时，不需要重新审批。

## 管理单元

用 `my-slides units add <id> --chapter <大章节> --title <小章节名>` 新增小章节，或用 `units move`、`units rename`、`units retitle` 调整清单；无需手工编辑 `units.json`。`retitle` 只改显示名，已有批准仍然有效。跨大章节移动要求用户重新确认报告，报告内容没变时保留 Spec 批准。结构变化后运行 `my-slides next --json`，按建议重建整套 Slides 并重新检查。

`my-slides next --all` 可一次列出当前待办并按 Agent / 用户分组；仅计划做到结构检查时可加 `next --no-browser`，不会改变 `export` 的浏览器检查门槛。`my-slides agent doctor` 检查项目内的工作流指引是否与当前包一致，不会覆盖用户修改。`my-slides clean` 默认只预览 30 天前的 `work/` 交接和 Wiki 快照；新旧交接混放时仍能列出过期文件。确认清单后添加 `--yes` 才删除。可用 `--older-than-days` 调整保留天数。

```text
my-slides units add <id> --chapter <章节> [--title <小章节名>] [--after <id>]
my-slides units retitle <id> <小章节名>
my-slides units move <id> [--after <id> | --before <id>] [--chapter <章节>]
my-slides units rename <old-id> <new-id>
my-slides units remove <id> [--json]          # 只预览影响
my-slides units remove <id> --yes              # 移入可恢复回收区
my-slides units trash list [--json]
my-slides units restore <trash-id>
```

## 调整大章节

`my-slides chapters list/add/rename/remove/move` 一次更新 `project.yaml`、`units.json` 与 `wiki/index.md` 三处存储。改名只改 `chapter` 字段，报告与 Spec 批准绑定的内容哈希与依赖指纹不变，无需重新批准。删除大章节时仍有小章节引用会拒绝；移动后运行 `next --json` 按建议重新组装报告并重建整套 Slides。

```text
my-slides chapters list
my-slides chapters add <章节名> [--after <已有章节>]
my-slides chapters rename <原名> <新名>
my-slides chapters remove <章节名>           # 仍有小章节时拒绝
my-slides chapters move <章节名> [--after <章节> | --before <章节>]
```

## 交付成品

整套 Slides 全部批准、构建和检查都是最新版本后，用 `my-slides export [--output DIR]` 导出一份 `<项目名>-v<序号>-<日期>.html`，并在 `.state/deliveries.json` 记录交付时间、版本号与包含的单元 SHA-256。`status --json` 会显示最近一次交付与自该交付以来发生变化的单元（按报告、Spec、HTML 哈希分别列出原因）。

`my-slides units remove <id>` 默认只显示影响预览，包括文件、批准和依赖/链接。预览确认无阻碍后添加 `--yes`，单元会移入 `my-slides/.state/trash/`，不会永久删除。若单元曾获报告或 Spec 批准，Agent 必须先取得用户明确同意再执行。命令会打印恢复命令；也可运行 `my-slides units trash list` 查看记录，并用 `my-slides units restore <trash-id>` 按原章节和位置恢复。清理回收区将在后续版本提供。

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
my-slides slides check --all --browser --screenshots  # 保存三视口截图及 contact sheets
my-slides slides visual-review --unit <id> --images contact-desktop.png contact-mobile-portrait.png contact-mobile-landscape.png --notes "观察与修订结论"
```

也可用 `--changed` 或 `--all`。默认的 `slides check` 只做结构检查；加 `--browser` 才跑桌面/手机视口测量（溢出、字号、对比度、导航等）。再加 `--screenshots` 落盘证据；`visual-review` 只记 Agent 看图结论，不代替用户批准，也不改变 `export` 门槛。证据目录在 `my-slides/.state/visual/<deck-sha>/`。

`my-slides next --json` 返回下一步命令、目标单元、原因和执行者（`agent` 或 `human`）。Agent 遇到 `actor: human` 必须停下，请用户自行审阅并执行 `confirm`。`approve` 只记录文件内容与依赖的待审版本；`confirm` 不提供 `--json` 或批量确认，要求在交互终端输入审阅者姓名与针对当前 SHA-256 的确认文字。状态文件记录姓名、本机账户与批准时间。申请后若文件或依赖变化，确认会拒绝，必须重新提交。完成报告确认后运行 `assemble`。

用户也能驳回待审申请或撤回已批准内容。`reject report|spec --unit <id> --reason "..."` 清除待审申请并记录驳回原因、时间和通道，仅针对本次待审版本；已批准的报告、Spec 不会因此作废。沿用 `confirm` 的同一种门（`--via chat` 要求 `--phrase` 和 `--user-reply`；`approval_mode: terminal` 要求交互终端）。`review` 在待审包里同时给出 `APPROVE` 与 `REJECT` 短语；对话驳回只接受 `REJECT` 短语，避免误用批准短语。`withdraw report|spec --unit <id>` 供 Agent 取消自己的待审申请，不需要用户门。`revoke report|spec --unit <id> [--reason ...]` 撤回已批准的内容；`--via chat` 时先跑一次拿到已批准版本信息与 `REVOKE` 短语，再带 `--phrase` 与 `--user-reply` 执行；终端模式沿用确认门。报告撤回会同时作废下游的 Spec 批准和该单元的 HTML/检查，`.state/approved/` 下的已批准副本仍可追溯。`status --json` 列出 `rejected_units` 与驳回理由；`next --json` 在重新提交审批后推荐 `review`，只有未补交待审申请时才提示按驳回意见修改并重新提交。

交接材料使用固定路径 `my-slides/work/wiki.md`、`my-slides/work/wiki-question.md` 和 `my-slides/work/<report|spec|slides>/<id>.md`；再次 `prepare` 会更新同一路径。`status --json` 的 `approvals.<kind>.current` 按选定单元计算，仅在其批准版本仍有效且有审阅者姓名和本机账户时为真；另列出待确认、需重审、已驳回及旧版无审阅者记录的单元。旧批准必须重新确认才能继续组装报告或构建 Slides。`slides.current` 表示构建有效，`slides.checked_current` 表示浏览器检查有效。

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
my-slides approve report --unit <id>          # 或 --chapter <大章节>
my-slides review report --unit <id>           # 贴到对话里，等用户明确批准
my-slides confirm report --unit <id> --via chat --phrase "..." --user-reply "..."
my-slides reject report --unit <id> --reason "..." --via chat --phrase "..." --user-reply "..."
my-slides assemble
my-slides prepare spec --unit <id> && …撰写… && my-slides validate spec --unit <id>
my-slides approve spec --unit <id>
my-slides review spec --unit <id>
my-slides confirm spec --unit <id> --via chat --phrase "..." --user-reply "..."
my-slides prepare slides --unit <id> && …按 Spec 页数写 HTML…
my-slides slides build --all
my-slides slides check --all
```

在 `project.yaml` 里设置 `reviewer: "姓名"`。默认 `approval_mode` 是 `chat`：Agent 先运行 `review`，把内容贴到对话里，等你明确批准后再运行 `confirm --via chat`。审批记录会保存通道和你的原话。对话审批依赖 Agent 遵守规则，程序无法分辨「你说了批准」和「Agent 声称你说了批准」。需要终端确认时，写成 `approval_mode: terminal`。建议不要把 `my-slides confirm` 放进编辑器的自动运行白名单，这样每次确认仍会在对话里多一步由你点选。

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
