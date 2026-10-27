# 测试说明

## GitHub Actions

[CI 工作流](../.github/workflows/ci.yml)在 PR、推送到 `main` 和手动触发时，在 Ubuntu 24.04、macOS 15、原生 Windows 2025 上使用 Python 3.11：检查 PR 版本与 CHANGELOG，安装本包，用 `scripts/sync-skill-templates.py --check` 确认 skill 镜像没有漂移，再跑全部单元测试。

Design+Slides 引擎在私有仓库里，CI 拿不到，所以真实引擎集成测试（`tests/test_design_deck.py` 的 `DesignEngineIntegrationTests`）在 CI 中会 **skip**。这部分只能在本地用完整测试验证；Mac / Windows 实机上的 5173 审阅与手改同样需要另外记录。

## 快速测试（默认）

不需要 Design 引擎；缺 `MY_SLIDES_DESIGN_ROOT` 时引擎集成用例会 skip。

```bash
./scripts/run-quick-tests.sh
# 或
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 完整测试（门禁）

先准备好 Design+Slides（Node 22.23+ / 24.22+，在引擎目录运行 `npm install` 和 `npm run build`），再用 `MY_SLIDES_DESIGN_ROOT` 指向它。引擎没就绪时脚本直接失败，不会悄悄跳过集成测试。

```bash
export MY_SLIDES_DESIGN_ROOT=<design-and-slides 目录>
./scripts/run-full-tests.sh
```

脚本依次检查引擎状态、skill 镜像，然后跑全部测试。Windows 上用 Git Bash 运行即可。

## `slides check`：结构 vs 渲染

| 命令 | 需要什么 | 检查什么 |
| --- | --- | --- |
| `my-slides slides check [--unit\|--all]` | Design 引擎（不需要宿主运行） | Design `check`：`deck.json` 与 `slides/*.html` 结构；my-slides 另查每个单元都有页面 |
| `… --browser` | 另需 5173 宿主正在运行 | Design 渲染检查：页面能否渲染、有无运行时警告 |

Design 不做自动视觉审阅；页面好不好看由用户在 5173 上看。

## 建议验收清单

- 快速套件绿；本地完整套件绿（含真实引擎集成测试）。
- 报告未批准时 `slides build` 被拒绝。
- `slides build --all` 生成的 `deck.json` 页序与 `units.json` 一致，缺页单元有占位页。
- 无 `units.json` 的项目被 CLI 拒绝。
- 新人只读 README + `skills/my-slides-workflow/SKILL.md` 可走通「报告 → Design deck → 5173 审阅 → 导出」。
