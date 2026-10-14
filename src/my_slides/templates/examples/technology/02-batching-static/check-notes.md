# 预期检查与人工审阅

- 片段 parser：两版各一页、各有合法 slide-notes；静态 SVG 无外链与脚本。
- 浏览器：桌面 SVG 五步和两条取舍说明均可读；390×844 与 844×390 无裁切，窄屏为有序列表。脚注使用 `.boundary.note`，按 note 字号阈值检查。
- 实测（2026-10-14）：对 `page.html` / `text-only.html` 跑三视口 `check_deck` + 截图均 `valid=true`；证据在收尾目录 `issue-38-closeout/`（不进包）。
- 人工事实审阅：只能解释队列与批次的概念，不能推出任何具体加速倍数、成本改善幅度或某项目实现细节。
- 类比边界：框大小和箭头长度无量化含义；省略连续批处理、prefill/decode、取消、缓存与优先级。
- 读者理解试验：见 `pilot-evaluation.md`；未完成，不阻塞工程 Issue 关闭。
