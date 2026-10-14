# Slides reference

Open when converting an approved Spec into HTML (`slides/pages/<id>.html`) or when reviewing the built deck.

## 工作流

1. `my-slides prepare slides --unit <id>` → 交接材料写入 `my-slides/work/slides/<id>.md`，**会按 Spec 主题从 example 索引中挑出 1–2 条最相关的参考案例路径与摘要**（不是把整个示例库倾倒到上下文里）。
2. 写 `slides/pages/<id>.html`：每个 Spec 页对应一个 `<section class="slide">`。
3. `my-slides slides build --unit <id>`：把 `<style>` 包裹在 `@scope` 内，加入壳、字体、导航，输出 `slides/previews/<id>.html`。
4. `my-slides slides check --unit <id>`：结构检查（页数 = Spec 页数，每页有 `slide-notes` JSON，图表 / 图标范围合规）。
5. 运行 `my-slides slides check --all --browser --screenshots`，会用 Playwright Chromium 测三视口并将每页 PNG、三个 contact sheet、`measurements.json` 存到 `my-slides/.state/visual/<deck-sha>/`。先打开全部 contact sheet；有问题的页打开 1× PNG，并对图表、表格和脚注放大至 2–4×。记录问题、修复和未解决项；修改后重新 build/check/看图。
6. 实际看图后运行 `my-slides slides visual-review --unit <id> --images contact-desktop.png contact-mobile-portrait.png contact-mobile-landscape.png --notes "观察、修复、未解决项"`。这只是 Agent 审阅记录，不是用户批准。`status --json` 的 `slides.visual` 单独显示证据和审阅是否仍匹配当前 deck/Spec/规则。截图本身不代表视觉通过。

## HTML 写法

- 根元素必须是 `<section class="slide">`（或 `<div class="slide">`）。同一小章节内不允许嵌套 slide。
- 必填属性：
  - `data-unit-id="<unit-id>"`，与单元 ID 完全一致。
  - `data-page-role="cover" | "content"`，与 `units.json` 中该单元的角色一致。
  - 推荐额外带 `data-unit-page="<N>"`（在整套 deck 中的页码），便于跨页编号。
- 每页必须有一个 `<script type="application/json" class="slide-notes">…</script>`，内容是 JSON 对象；不要同时放两个 `slide-notes`。
- 图表用 `<script type="application/json" class="mls-echarts-spec">…</script>`；图标用 `<script type="application/json" class="mls-lucide-spec">…</script>`。每个标记只承载一种资产；只能使用 Spec 中声明的图表类型 / lucide 图标名。
- 自定义样式用 `<style>`，但要保证大括号配对；`slides build` 会用 `@scope` 包裹章节避免污染其他单元。`style="…"` 中不能出现 `url(` 或 `@import`。
- 不能用 `<script>` 跑 JS；不能加载 CDN；不能放 `<iframe>`、`<form>`、`<video>` 等禁用的标签。完整白名单与禁项见 `src/my_slides/slide_fragments.py`。

## 视觉规则快速回顾

更多细则与反例见 `references/visual-rules.md`：

- 一页只承载一个唯一结论；超过两个并列结论时拆页。
- 数字、单位、日期、来源贴近对应句子；不要把它们集中堆到页面底部。
- 删除和拆页优先于缩小字号。文本过长就拆到下一页，而不是把字号挤到 12px。
- 字体与行长阈值要看视口 + 文本角色（标题 / 正文 / 脚注），不按「整页最多 N 字」一刀切。
- 同一组内字号对比 ≥ 1.5x；同页字号档位不超过 3 档。

## 常见错误

- slide 嵌套：禁止 `<section class="slide">` 内再出现 `<section class="slide">`。
- 单元 ID 错配：每个 slide 的 `data-unit-id` 必须等于 `units.json` 中该单元的 ID。
- 图表 / 图标越界：某页用了 Spec 没声明的 echarts 图表类型或 lucide 图标。
- 阅读字号：浏览器测标题/正文/注释和 SVG 图内文字的实际显示尺寸；桌面阈值分别为 18/14/11px，手机竖屏 12/10/8px，横屏 11/9/7px。确有必要的局部例外可用 `data-qa-small-text="allowed"`，需要在视觉审阅记录中说明。ECharts 若将字转成路径，程序无法读出这些字，必须看截图。手机视口（竖屏 / 横屏）的图表内文字低于阈值会作为 `warnings` 提示，由人工看截图核对而不阻塞交付；桌面则视为硬错误（标题 / 正文 / 注释 / SVG 图内文字均不可低于阈值）；SVG 之外溢出图表边界的标签始终是错误。
- slide-notes 缺失或重复。
- `<style>` 中不配对或注入了外部资源。
- CDN：把所有外部链接 / CDN 改成内嵌资源；白名单之外不允许任何外部 URL。

## 边界

- `slides build` 只处理已批准 Spec；未批准的 Spec 不会进入 deck。
- `slides check --browser` 跳过渲染器/浏览器缺失的环境并标记 skip；CI 完整门禁要求 `scripts/run-full-tests.sh`。
- 撤回报告会让下游 Spec 与 HTML/检查一起失效；需要走完报告 → Spec → 重建 → 重新检查。
