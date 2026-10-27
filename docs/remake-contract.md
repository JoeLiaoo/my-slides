# 0.8.0 薄壳契约

my-slides 是 Agent 驱动工作区及确定性 CLI 辅助。CLI 不会自己写文章、长文 HTML 或幻灯内容；外部 skill 是给当前 Agent 的指令，不是可直接执行的子进程。未找到真实 runner 时，`present` 输出交接任务、`pending_agent` 或 `failed`，退出码非零。

## 目录与配置

```text
<项目>/
  materials/raw/                 # 可用既有原材料位置；原资料只读
  my-slides/
    project.json                 # 新模式唯一配置
    article.md                   # 默认共享内容基准；可引用项目内既有正文
    beautiful/article.html       # 可选，外部 skill 制作
    design/deck/deck.json        # 可选，Design 项目
    design/deck/slides/*.html
    design/deck/assets/
    exports/                     # 可选离线导出
```

`init` 只创建 `my-slides/project.json`，其中 `present` 为 `{}`。所有配置路径均相对**项目根**，不相对配置文件或当前工作目录。输入须在项目内；新输出须在 `my-slides/` 内，不能与输入或另一目标重叠。`schema_version` 与包版本不同；首版仅接受 1 和以下两个 provider。

已核对外部入口：`writing-shape` 与 `writing-beats` 各接收原料 Markdown，由 Agent 与用户逐段成文，没有 CLI runner；`beautiful-article` 接收 Markdown 等素材，经其自身计划、确认和构建步骤交付单文件 `article.html`，没有供本壳直接调用的生成 CLI；Design slides skill 指导 Agent 创作 deck，Design Agent CLI 提供 `check <project> --strict`、`apply`、`render-check` 和 `export` 等确定性动作。Agent 应先阅读实际安装版本的 skill，再把完成的 beautiful 文件安全交接到配置输出路径；若输出已有手改，先核对差异，不直接覆盖。

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

目标键存在即启用；删除键不删除已有成果。`present` 处理全部启用目标，`present --target NAME` 只处理该目标且不改配置。空目标集报错。已有非空正文可直接使用，写作 skill、Wiki、Report、`research/numbers.md`、固定章节和旧审批都不是新路径的前置条件。正文保留来源、日期、数字口径和待补项；呈现继承引用，不编造缺失证据。

## 内容与完成语义

正文是共享内容基准；beautiful 与 slides 有各自可编辑产物。呈现可删减、重组和改版式，不能静默增加结论或数字。用户在 5173 改了实质内容，Agent 应回写正文并更新另一目标，或明确记录为该目标差异；不做自动双向同步。文章变化提示两目标待更新，不授权覆盖手改页面。

`present` 按目标依次处理，即使一个目标失败也继续另一个。`pending_agent` 表示仅交接；`failed` 表示本次检查或依赖失败；`succeeded` 仅表示 CLI 已完成的确定性检查（当前 slides 为 Design `check --strict`），不等于生成、渲染、事实核对或用户认可。全部所选目标 `succeeded` 才退出 0，否则退出 1。结果分别给出输入指纹、输出路径/指纹、检查、渲染及人审状态。旧有效产物存在也不代表本次成功；失败不覆盖其文件。重试指定目标，不触碰另一目标。

Design 根目录继续由 `MY_SLIDES_DESIGN_ROOT` 提供。Design 项目名是 `deck`，projects 根为 `<项目>/my-slides/design`。Agent 用引擎 `apply` 更新在线页面，提交前重读文件并使用基线冲突检查；连接失败、超时或 409 必须保留现场，不能回退直写盘。使用 5173 前核对宿主实际挂载项目，不能只检查端口可访问。结构检查、浏览器渲染和 Joe 的视觉审阅分别记录；可选离线导出由引擎完成，不隐含上传。

## 迁移与回退

先复制 0.7 项目，盘点文章候选、完整 Design deck、素材、页序、用户手改及旧审批。只在复制件添加 `project.json`，引用现有正文或由 Agent 明确编写新正文；保留 `project.yaml`、`units.json`、Wiki、Report、`.state` 及全部历史成果。旧报告审批不自动批准新正文，旧 deck 与新正文的一致性初始为未知。新模式不调用旧 `slides build` 同步器；不要让两版本共写同一 deck。复制件验收通过后才切换日常项目。回退使用未改动的 0.7 副本与对应工具版本；新增成果需单独复制核对。

## RSI 样例七条验收（Phase B，尚未完成）

1. 仅非空正文与双目标配置可走新路径；不触发 Wiki、Report、units、numbers 或旧审批，输入前后哈希一致。
2. 双目标独立产出；分别模拟 provider 缺失，单目标重试不改另一份产物，总体状态诚实。
3. 逐项核对数字、引语、结论、来源和待补项，无正文外新增论断。
4. Design 全 deck `check --strict` 零错零警告，正确项目的宿主 `render-check` 通过，Joe 在 5173 审阅；错误项目宿主拒绝写入。
5. 一页手改后修另一页不覆盖；同页冲突和断线不直写；正文变化时两目标标为待更新。
6. 离线导出由引擎完成，不覆盖同名文件；断网且宿主停止后仍能阅读和翻页。
7. 0.7 复制件迁移与重复迁移不丢页序、附加页、素材、手改或历史；旧副本可回退，并验证 Windows 与另一系统的中文/空格路径和不同 cwd。

本 PR 交付契约与最小壳。RSI 端到端样例和删除旧 CLI 另行实施。
