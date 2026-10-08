# My Slides

面向投资研究的本地 Agent 工具。用户在投资项目目录中使用 Codex、Claude Code 或 DeepSeek harness，通过统一 CLI 整理项目资料、维护 Wiki、撰写投资报告，并生成可离线浏览的 HTML 投资汇报 Slides。

工具由本地 CLI 与当前 Agent 协同工作：Agent 负责分析与内容生成，工具负责项目文件组织、来源追溯、版本和审阅状态、图表图标渲染及 Slides 检查。当前以 Markdown 为资料输入，文档转换由用户预先完成。

## 目标工作流（v2 单元格式）

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

每个单元有稳定 ID（见 `my-slides/units.json`），对应一份报告、一份 Spec、一页 HTML。改单元 A 时只处理 A 及真正依赖它的部分。

## 迁移窗口（v1 → v2）

**新项目默认 v2。** `my-slides init` 会创建 `units.json` 与 `reports/units/`、`specs/units/`、`slides/pages/` 等目录，不再把 `slides/chapters/` 当作主路径。

仍在使用 **v1 章节格式**（无 `units.json`、按章整文件）的项目在弃用窗口内可继续运行，但 `status` / `doctor` / `prepare` 会提示迁移。`--json` 输出含 `"deprecated": true`。设置 `MY_SLIDES_ALLOW_V1=1` 可暂时静默人机警告（JSON 仍标记 `deprecated`）。

### 如何迁移

```text
my-slides migrate --to-units --dry-run --project <路径>   # 只读预检
my-slides migrate --to-units --project <路径>            # 正式迁移（先备份）
my-slides migrate --rollback --project <路径>            # 回滚最近备份
```

窗口结束后将删除 v1 章节主路径；请在真实项目上完成迁移后再依赖新版本。

### 窗口期内还能做什么 / 不能指望什么

| 能做 | 不要指望 |
| --- | --- |
| 旧 v1 项目继续 prepare / validate / approve / slides build | 新 `init` 再创建 v1 默认结构（需显式 `--format v1`，且已弃用） |
| `migrate --dry-run` / 正式迁移 / 回滚 | 永久双轨；阶段 9 将移除 v1 |
| v2 按单元批准、增量构建与检查 | 把整套旧批准自动继承为所有单元已批准 |

## 开始使用

在仓库根目录安装开发版 CLI：

```powershell
uv tool install --editable ".[browser]" --link-mode copy --cache-dir .uv-cache
my-slides renderer install
my-slides browser install
my-slides init --project "C:\Projects\某投资项目"
my-slides agent install --project "C:\Projects\某投资项目"
my-slides doctor --project "C:\Projects\某投资项目"
my-slides sources scan --project "C:\Projects\某投资项目"
my-slides prepare wiki --project "C:\Projects\某投资项目"
```

默认 `init` 得到 v2 项目。接着按单元推进：

```text
my-slides prepare report --unit <id>
my-slides validate report --unit <id>
my-slides approve report --unit <id>
my-slides prepare spec --unit <id>
my-slides approve spec --unit <id>
my-slides prepare slides --unit <id>
my-slides slides build --unit <id>
my-slides slides check --unit <id> --browser
```

也可用 `--changed` 或 `--all`。组装完整报告：`my-slides assemble`。

`my-slides agent install` 会在项目 `.agents/skills/` 与 `.claude/skills/` 安装工作流技能，并保留已有同名文件。包含图表或图标的项目需先运行 `my-slides renderer install`；使用 `slides check --browser` 前运行 `my-slides browser install`。渲染依赖固定为 ECharts 6.1.0 与 lucide-static 1.52.0。

## 当前状态

- **v2（默认）**：单元清单、依赖与状态、按单元 prepare/validate/approve、报告组装、增量 slides build/check、正式迁移与回滚。
- **v1**：弃用窗口内仍可用；请计划迁移。
- 生成内容仍由当前 Agent 撰写；真实项目需逐页审阅。

运行基础回归测试：

```powershell
$env:PYTHONPATH = "src"
$env:MY_SLIDES_RENDERER_HOME = Join-Path $env:LOCALAPPDATA "MySlides\renderer"
python -m unittest discover -s tests -v
```

实施计划见 [`docs/plans/local-investment-wiki-slides.md`](docs/plans/local-investment-wiki-slides.md)，报告章节主题见 [`docs/templates/投资报告章节.md`](docs/templates/投资报告章节.md)。
