# My Slides

研究成文的多格式呈现工作区。0.8.0 新项目默认使用薄壳：Agent 以原始材料或已有正文为基础完成 `article.md`，再选择 beautiful 长文和/或 Design+Slides 幻灯。Wiki/Report 可在外部按需整理，不是必经步骤。

## 新项目：先做什么，怎样算完成

```text
my-slides init --project "<项目目录>"
# 编辑 <项目>/my-slides/project.json 的 present，选择 beautiful、slides 或两者
# 由 Agent 用 writing-shape / writing-beats 等外部工具，或直接引用已有成文
# 保存非空 article.md；保留来源、日期、口径及待补项
my-slides present --project "<项目目录>" --json
my-slides present --project "<项目目录>" --target slides --json
```

`present` 会逐目标输出状态和下一步。缺少可执行 provider 时是 Agent 交接，不会声称 CLI 自动生成成品；未完成时退出非零。beautiful 即使已有 HTML 仍为 `pending_agent`，由 Agent 核对后说明完成情况。Design 的 `succeeded` 只表示 `check --strict` 通过；内容同步状态始终为 `unknown`，仍需 Agent 对照正文、运行渲染检查，并由你在 5173 审阅。使用 Design 时设置 `MY_SLIDES_DESIGN_ROOT`，宿主 projects 根为配置输出 `deck` 的父目录（默认 `<项目>/my-slides/design`）；在线编辑走引擎 `apply`，连接失败不直写。详细路径、示例配置、迁移和失败语义见 [薄壳契约](docs/remake-contract.md)。

以下章节记录保留的 0.7 单元工作流，仅供显式 `my-slides init --legacy` 的旧项目使用。新项目不运行其中的审批、`slides build` 或按单元交付命令。

[![CI](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml)

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告；报告经用户批准后，Agent 在 [Design+Slides](#先装这些) 里写演示页面，用户在 `127.0.0.1:5173` 上审阅、手调，最后导出一份可离线打开的 HTML。

项目以 `my-slides/units.json` 中的小章节（单元）组织：每个小章节属于一个大章节，对应一份报告和 Design deck 里的一页或多页。审批、修改和增量同步都以小章节为单位。

**分工：my-slides 管内容与流程（资料 → Wiki → 报告 → 审批 → 交付记录）；Design+Slides 管页面格式、编辑器和导出。**

## 工作流

```text
项目 Markdown 资料
        ↓
项目 Wiki 与来源追溯
        ↓
报告小章节（reports/units/<id>.md）→ 提交申请 → 在对话中按小章节或整章确认
        ↓
组装整份报告 + 整理可复核的公开数字（research/numbers.md）
        ↓
Agent 按已批准报告写 Design 页面（design/deck/slides/<id>.html，可多页）
        ↓
你在 127.0.0.1:5173 审阅：小改自己手调，大改口述给 Agent
        ↓
导出离线 HTML，并记录交付版本
```

只有报告需要你审批。页面版式怎么改都不需要重新审批；页面上的结论或数字要改，先改报告并重新审批。设计背景见 [`docs/plans/design-slides-migration.md`](docs/plans/design-slides-migration.md)，试点记录见 [`docs/plans/spike-results.md`](docs/plans/spike-results.md)。

## 先装这些

| 用途 | 需要先有 | 然后 |
| --- | --- | --- |
| 使用命令 | Python 3.11+ 和 [uv](https://docs.astral.sh/uv/) | 下面的 `uv tool install` |
| 写页、审阅、导出 | Node.js 22.23+ 或 24.22+，以及 design-and-slides 目录 | 在该目录运行 `npm install` 和 `npm run build`，再设置 `MY_SLIDES_DESIGN_ROOT` |

只做资料整理和报告时，有 Python 和 uv 即可。Design+Slides 不随本仓库分发（它使用 BaoCut Community License，不是 MIT），目前取自 `JoeLiaoo/lzj-skill` 的 `vendor/design-and-slides`。

```powershell
cd <design-and-slides 目录>; npm install; npm run build
$env:MY_SLIDES_DESIGN_ROOT = "<design-and-slides 目录>"   # 长期使用请写进系统环境变量
```

```bash
cd <design-and-slides 目录> && npm install && npm run build
export MY_SLIDES_DESIGN_ROOT="<design-and-slides 目录>"     # macOS：写进 ~/.zshrc
```

## 开始使用

克隆仓库，在仓库目录中安装命令：

```bash
git clone https://github.com/JoeLiaoo/my-slides.git
cd my-slides
uv tool install --editable . --link-mode copy --cache-dir .uv-cache
my-slides help
```

`my-slides help` 向 Agent 说明工具职责、完整流程、逐单元命令和需要你审阅的节点；在项目目录外也能运行。`my-slides --help` 显示命令列表，`my-slides <命令> --help` 显示参数，`my-slides help --json` 输出可供 Agent 读取的 JSON。

这是可编辑安装；更新工具时保留该目录并运行 `git pull`。然后为投资项目初始化工作区（将占位路径换成实际路径）：

```text
my-slides init --legacy --project "<投资项目目录>"
my-slides agent install --project "<投资项目目录>"
my-slides doctor --project "<投资项目目录>"        # design.ready 为 true 才能写页
my-slides next --project "<投资项目目录>" --json
```

按单元推进：

```text
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>       # Agent 提交待审申请，不会批准
my-slides review report --unit <id>        # 贴到对话里，等你明确批准
my-slides confirm report --unit <id> --via chat --phrase "..." --user-reply "..."
my-slides assemble
my-slides prepare evidence-research && my-slides validate evidence-research
my-slides prepare slides --unit <id>       # 写页交接；Agent 按它写 design/deck/slides/<id>.html
my-slides slides build --all               # 按 units.json 同步页序与分节；只给缺页单元补占位页
my-slides slides check --all [--strict]    # Design 结构检查，并核对每个单元至少有一页
my-slides slides open                      # 输出审阅链接和启动宿主的命令
my-slides export [--output <目录>]          # 宿主运行时导出离线 HTML 并记录交付
```

也可用 `--changed` 或 `--all` 代替 `--unit`。`my-slides next --json` 返回下一步命令、目标单元、原因和执行者（`agent` 或 `human`）；Agent 遇到 `actor: human` 必须停下交给你。`my-slides next --all` 一次列出全部待办并按 Agent / 用户分组。

## 在 5173 上审阅和手改

在 design-and-slides 目录启动宿主，指向本项目的 deck 所在目录：

```text
npm run dev -- --projects "<投资项目目录>/my-slides/design"
```

然后打开 `http://127.0.0.1:5173/open/slides/deck`（`my-slides slides open` 会打印准确链接和命令）。

- 小改（改字、挪位置、换颜色）直接在编辑器里做，保存即写回 `slides/*.html`。
- 大改口述给 Agent。Agent 改页前会重新读文件，在你改过的内容上改。
- 宿主运行时，`slides build`、`units remove/restore/rename` 通过宿主发布，打开的编辑器会自动刷新；如果你正在改同一个文件，命令会停下来报冲突，不会覆盖你的修改。
- 同一单元的多页命名为 `<id>.html`、`<id>_2.html`……；不属于任何单元的页（例如你手加的议程）保留在原位置。
- `slides check --browser` 和 `export` 需要宿主在运行；`slides check` 不需要。Design 不做自动视觉审阅，好不好看由你判断。

## 交付成品

你满意后，在宿主运行时运行 `my-slides export [--output DIR]`：它先确认每个单元的报告都有当前有效批准、每个单元都有页面，再导出 `<项目名>-v<序号>-<日期>.html`，并在 `.state/deliveries.json` 记录交付时间、版本号、各单元报告与页面的 SHA-256。`status --json` 显示最近一次交付，以及之后报告或页面变过的单元。

## 审批

在 `project.yaml` 里设置 `reviewer: "姓名"`。默认 `approval_mode` 是 `chat`：Agent 先运行 `review`，把内容贴到对话里，等你明确批准后再运行 `confirm --via chat`，审批记录保存通道和你的原话。需要终端确认时写成 `approval_mode: terminal`，由你本人在交互终端运行 `confirm`。建议不要把 `my-slides confirm` 放进编辑器的自动运行白名单。

你也能驳回或撤回。`reject report --unit <id> --reason "..."` 清除待审申请并记录原因，只针对本次待审版本，已批准的报告不受影响；对话驳回只接受 `review` 给出的 `REJECT` 短语。`withdraw report --unit <id>` 供 Agent 取消自己的申请，不需要你确认。`revoke report --unit <id> [--reason ...]` 撤回已批准的报告：`--via chat` 时先跑一次拿到 `REVOKE` 短语，你同意后再带 `--phrase` 与 `--user-reply` 执行；`.state/approved/` 下的已批准副本仍可追溯。`status --json` 列出 `rejected_units` 与驳回理由。

对话审批和交互终端只能减少误操作，**不能阻止 Agent 有意绕过**：程序无法分辨「你说了批准」和「Agent 声称你说了批准」，Agent 也可能通过伪终端或改写本地状态伪造确认。请亲自核对 `status --json` 里的审批人和时间；需要可验证的强制人审，必须使用独立身份与权限的外部审批系统。

## 管理单元

用 `my-slides units add <id> --chapter <大章节> --title <小章节名>` 新增小章节，或用 `units move`、`units rename`、`units retitle` 调整清单；不要手工编辑 `units.json`。`retitle` 只改显示名，已有批准仍然有效。跨大章节移动要求你重新确认报告。结构变化后运行 `slides build --all` 和 `slides check --all`。

```text
my-slides units add <id> --chapter <章节> [--title <小章节名>] [--after <id>]
my-slides units retitle <id> <小章节名>
my-slides units move <id> [--after <id> | --before <id>] [--chapter <章节>]
my-slides units rename <old-id> <new-id>      # 页面文件名和 deck.json 引用一起改
my-slides units remove <id> [--json]          # 只预览影响
my-slides units remove <id> --yes              # 报告和页面一起移入可恢复回收区
my-slides units trash list [--json]
my-slides units restore <trash-id>             # 恢复报告、页面和原来的页序
```

若单元曾获报告批准，Agent 删除前必须先取得你的明确同意。`my-slides clean` 默认只预览 30 天前的 `work/` 交接和 Wiki 快照，加 `--yes` 才删除；`my-slides agent doctor` 检查项目内的工作流指引是否与当前包一致。

## 调整大章节

`my-slides chapters list/add/rename/remove/move` 一次更新 `project.yaml`、`units.json` 与 `wiki/index.md`。改名不影响报告批准；删除仍有小章节引用的大章节会被拒绝；移动后按 `next --json` 重新组装报告并同步 deck。

```text
my-slides chapters list
my-slides chapters add <章节名> [--after <已有章节>]
my-slides chapters rename <原名> <新名>
my-slides chapters remove <章节名>
my-slides chapters move <章节名> [--after <章节> | --before <章节>]
```

## 从 0.6.x 升级

0.7.0 去掉了 Presentation Spec 和旧的 HTML 拼页流程（详见 [`CHANGELOG.md`](./CHANGELOG.md)）。已有项目：

1. 报告批准继续有效，不用重新审批。
2. 旧的 `my-slides/specs/` 和 `my-slides/slides/` 不再读取；`my-slides doctor` 会列出它们，确认不需要后自行归档或删除。
3. 设置好 `MY_SLIDES_DESIGN_ROOT` 后运行 `my-slides slides build --all` 生成 Design deck，再按 `next --json` 让 Agent 逐单元写页。旧 HTML 页面可以给 Agent 当参考，但要按 Design 格式重写。
4. 安装时不再需要 `[browser]`，也不再需要 `renderer install` / `browser install`。

### 版本

用 `my-slides --version`（或 `-V`）查看版本。开发 checkout 会同时显示短提交号；工作区有改动时会标记“有未提交修改”。`my-slides help --json` 也会返回 `version`、`commit` 和 `dirty`。

每个 PR 都要按影响选择版本级别，在 [`CHANGELOG.md`](./CHANGELOG.md) 添加对应版本条目。兼容新增、修复和文档升 patch；不兼容的命令或状态变化升 minor 并把 patch 归零，更新日志必须有“不兼容变更”分类；major 版本需要维护者批准。只改 `.github/`、`tests/` 或 `scripts/` 的 PR 可以不升版本。测试通过后，CI 会给 `main` 上尚未打过的版本自动创建并推送 `vX.Y.Z` tag。规则见 [`docs/versioning.md`](docs/versioning.md) 与 [`AGENTS.md`](./AGENTS.md)。

## 测试

PR、推送到 `main` 和手动触发时，[GitHub Actions](.github/workflows/ci.yml) 在 Ubuntu、macOS 和 Windows 上用 Python 3.11 跑全部测试，并检查 skill 镜像没有漂移。Design 引擎在私有仓库，CI 里的引擎集成测试会跳过，需要本地验证：

```bash
./scripts/run-quick-tests.sh          # 快速：没有 Design 引擎时集成测试跳过
./scripts/run-full-tests.sh           # 完整：要求 MY_SLIDES_DESIGN_ROOT 就绪，否则失败
```

Windows 用 Git Bash 运行上面两个脚本即可；也可以在 PowerShell 里直接跑：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

说明见 [`docs/testing.md`](docs/testing.md)。

## 许可

本项目采用 [MIT 许可证](LICENSE)。Design+Slides 不包含在本仓库中，使用时遵守它自带的 BaoCut Community License。
