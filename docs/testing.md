# 测试说明

[CI 工作流](../.github/workflows/ci.yml)在 PR、推送到 `main` 和手动触发时，在 Ubuntu、macOS 和 Windows 上使用 Python 3.11，检查版本与 CHANGELOG、skill 镜像，并运行全部单元测试。

## 本地测试

无需 Design 引擎即可运行薄壳测试：

```bash
./scripts/run-quick-tests.sh
# 或
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

PowerShell 可设置 `$env:PYTHONPATH = "src"` 后运行 `python -m unittest discover -s tests -v`。

`./scripts/run-full-tests.sh` 先检查 `MY_SLIDES_DESIGN_ROOT` 指向已安装并构建的引擎，再检查 skill 镜像和运行同一套测试。Windows 上可用 Git Bash。真实页面的 `check --strict` 与渲染检查由 Design 引擎执行；用户还需在 5173 做视觉审阅。

`tests/test_thin.py` 覆盖配置与路径限制、非空 UTF-8 正文、目标隔离、产物保留、`content_sync: unknown` 和 Design strict 检查的完成语义。`tests/test_versioning.py`、`tests/test_sync_skill_templates.py` 分别覆盖版本规则和镜像同步。
