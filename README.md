# My Slides

研究正文的多格式呈现薄壳。Agent 从原始材料或已有正文完成 `article.md`，再选择 beautiful 长文、Design+Slides 幻灯或两者。CLI 只负责创建配置、逐目标交接和确定性检查；写作、页面制作、渲染与人审由 Agent 和外部工具完成。完整路径与完成语义见 [薄壳契约](docs/remake-contract.md)。

[![CI](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/JoeLiaoo/my-slides/actions/workflows/ci.yml)

## 安装与开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。克隆仓库后安装：

```bash
git clone https://github.com/JoeLiaoo/my-slides.git
cd my-slides
uv tool install --editable . --link-mode copy --cache-dir .uv-cache
my-slides help
```

```text
my-slides init --project "<项目目录>"
# 编辑 <项目>/my-slides/project.json 的 present，选择 beautiful、slides 或两者
# Agent 写入非空 UTF-8 正文，默认路径为 <项目>/my-slides/article.md
my-slides present --project "<项目目录>" --json
my-slides present --project "<项目目录>" --target slides --json
```

`init` 只写 `my-slides/project.json`，不会覆盖已有配置。原始项目资料保持只读；所有配置路径相对项目根。默认配置的 `present` 是空对象，需要选择目标。一个双目标配置示例：

```json
{
  "schema_version": 1,
  "article": "my-slides/article.md",
  "present": {
    "beautiful": {"provider": "beautiful-article", "output": "my-slides/beautiful/article.html"},
    "slides": {"provider": "design-and-slides", "output": "my-slides/design/deck"}
  }
}
```

`present` 会逐目标输出状态与下一步；未完成时退出非零。beautiful 即使已有 HTML 仍是 `pending_agent`，由 Agent 核对内容和引用。slides 的 `succeeded` 只表示 Design `check deck --strict` 通过；`content_sync` 始终为 `unknown`。Agent 仍须对照正文核对内容、运行渲染检查，并请用户在 5173 审阅。`--target` 只处理指定目标，不更改另一个目标。失败保留现有产物。

## Design+Slides

Design 引擎不随本仓库分发，使用其自带的 BaoCut Community License。需要 Node.js 22.23+ 或 24.22+，在 design-and-slides 目录运行 `npm install`、`npm run build`，并设置 `MY_SLIDES_DESIGN_ROOT` 指向该目录。页面格式由引擎的 `skills/slides/SKILL.md` 定义。

配置中的 slides 输出目录必须以 `deck` 结尾；其父目录是宿主的 projects 根。以上示例的宿主命令是：

```text
npm run dev -- --projects "<项目目录>/my-slides/design"
```

Agent 在线改页前须重读文件并通过引擎 `apply` 发布；连接失败或冲突时保留现场。Design 的渲染检查、5173 人审、可选离线导出由引擎完成，不由本 CLI 执行。

## 从旧项目迁移

在旧项目复制件中，选定现有成文或将报告正文整理成非空 `article.md`，再添加 `my-slides/project.json` 并配置目标。保留旧文件和审批记录作为历史；旧审批不会自动批准新正文。核对现有 deck 与正文、页序、素材和手改后再切换日常使用。旧 `project.yaml`、`units.json`、Wiki/Report 和审批命令已从本包删除；需要操作旧流程时使用对应旧版本。详见 [迁移说明](docs/remake-contract.md#迁移与回退)。

## 命令与版本

CLI 只有 `init`、`present`、`help` 和 `--version`（或 `-V`）。`my-slides help --json` 给 Agent 返回指南、版本、短提交号和工作区 dirty 状态；Git 元数据只在 `help` 和版本命令读取。开发 checkout 的版本输出会附提交与修改标记，正式安装显示包版本。

版本规则见 [docs/versioning.md](docs/versioning.md)。

## 测试

CI 在 Ubuntu、macOS 和 Windows 上运行 Python 3.11 单元测试及 skill 镜像检查。本地可运行：

```bash
./scripts/run-quick-tests.sh
```

或在 PowerShell 中：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Design 引擎就绪时可运行 `./scripts/run-full-tests.sh`；它先检查引擎与 skill 镜像。自动检查不替代用户在 5173 的视觉审阅。见 [测试说明](docs/testing.md)。

## 许可

本项目采用 [MIT 许可证](LICENSE)。Design+Slides 不包含在本仓库中，使用时遵守它自带的 BaoCut Community License。
