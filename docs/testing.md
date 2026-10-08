# 本地测试说明

本仓库**不使用 GitHub Actions**（账户无 Actions 额度）。完整回归请在开发机上跑本地脚本。

## 快速测试（默认）

不强制安装 Node 渲染器或 Chromium；缺少可选依赖时相关用例会 **skip**。

```bash
./scripts/run-quick-tests.sh
# 或
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 完整测试（门禁）

安装锁定版本的渲染器与 Playwright Chromium，并将「缺依赖」从 skip 改为 **失败**：

```bash
chmod +x scripts/run-full-tests.sh   # 首次
./scripts/run-full-tests.sh
```

等价环境变量：

| 变量 | 作用 |
| --- | --- |
| `PYTHONPATH=src` | 使用源码树中的 `my_slides` |
| `MY_SLIDES_FULL_TESTS=1` | 可选依赖未就绪时失败而非跳过 |
| `MY_SLIDES_RENDERER_HOME` | 渲染器安装目录（脚本会设默认值） |

前置：本机已安装 **Python 3.11+**、**Node.js / npm**。首次完整跑会下载 Chromium。

## `slides check`：结构 vs 浏览器

| 命令 | 需要什么 | 检查什么 |
| --- | --- | --- |
| `my-slides slides check [--unit\|--all]` | 仅已生成的 `slides/index.html` | 结构：生成器标记、`data-unit-id` 集合/顺序与 `units.json` 一致、唯一封面 |
| `… --browser` | 另需 `my-slides browser install`（Playwright Chromium） | 在桌面/手机视口逐页激活后测溢出、重叠、可见性等 |

快速套件默认不装浏览器；缺依赖时带 `--browser` 的用例会 skip。完整门禁用 `./scripts/run-full-tests.sh`。

## 建议验收清单（issue #1 §9 子集）

- 快速套件绿。
- 完整套件绿（含图表 SVG、浏览器桌面/手机视口）。
- 多单元：`--unit` 增量构建与 `--all` 全量构建在相同输入下内容一致；组装后每个单元恰好一个 `data-unit-id`（见 `tests/test_assembly.py`）。
- 无 `units.json` 的项目被 CLI 拒绝。
- 新人只读 README + `skills/my-slides-workflow/SKILL.md` 可走通单元化流程。
