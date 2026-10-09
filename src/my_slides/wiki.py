"""Wiki scaffolding, snapshots, and Markdown link validation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .project import now
from .units import MARKDOWN_LINK_RE, resolve_local_markdown_path, strip_markdown_code_regions, strip_markdown_link_target


def wiki_instructions() -> str:
    return """# Wiki 维护约定

本 Wiki 是项目持续积累的 Markdown 知识库。请先读 index.md，再按主题页阅读和更新知识；新资料到来时将内容整合进相关页面，补充页面间链接，更新索引，并在 log.md 追加简短记录。有价值的问答、比较和综合分析也可以沉淀为新页面。

使用自然语言和普通 Markdown。无需 frontmatter、固定标签、逐条事实分类或资料 ID。重要判断、数字口径、预测假设和不确定性在相关正文中直接说明。引用使用相对 Markdown 链接，尽量链接到原始资料或相关 Wiki 页面；从 Wiki 链接到项目根目录资料时，按页面所在层级计算相对路径。原始项目资料由 agent 只读。

索引按项目报告章节组织；同一主题页面可以出现在多个章节下。维护 Wiki 时顺手检查断链、过期信息、口径冲突、重复页面及缺少的关联。遇到矛盾时保留各自语境并用简洁文字指出待核实之处。
"""


def sync_wiki_index(path: Path, chapters: list[str]) -> None:
    if not path.exists():
        parts = [
            "# Wiki Index",
            "",
            "项目知识导航按报告章节组织。将相关主题页面链接放在对应章节下；同一页面允许出现在多个章节。",
            "",
        ]
        for chapter in chapters:
            parts.extend([f"## {chapter}", "", "<!-- 列出本章相关 Wiki 页面及一句话说明。 -->", ""])
        parts.extend(["## 补充研究", "", "<!-- 列出尚未纳入报告章节的研究页面。 -->", ""])
        path.write_text("\n".join(parts), encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8")
    headings = set(re.findall(r"^##\s+(.+?)\s*$", content, flags=re.MULTILINE))
    missing = [chapter for chapter in chapters if chapter not in headings]
    if not missing:
        return
    additions = "\n".join(f"## {chapter}\n\n<!-- 列出本章相关 Wiki 页面及一句话说明。 -->\n" for chapter in missing)
    extra_heading = re.search(r"^## 补充研究\s*$", content, flags=re.MULTILINE)
    if extra_heading:
        content = content[:extra_heading.start()] + additions + "\n" + content[extra_heading.start():]
    else:
        content = content.rstrip() + "\n\n" + additions + "\n## 补充研究\n\n<!-- 列出尚未纳入报告章节的研究页面。 -->\n"
    path.write_text(content, encoding="utf-8")


def snapshot_wiki(base: Path, stamp: str) -> Path:
    source = base / "wiki"
    target = base / ".state" / "snapshots" / "wiki" / stamp
    records = []
    for page in source.rglob("*.md"):
        relative = page.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = page.read_bytes()
        destination.write_bytes(content)
        records.append({"path": relative.as_posix(), "sha256": hashlib.sha256(content).hexdigest()})
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(json.dumps({"captured_at": now(), "files": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def markdown_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = strip_markdown_code_regions(path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        label = match.group(0)
        # Footnote references look like [^1]; definitions are handled as ref-defs.
        if re.match(r"^\[\^[^\]]+\]", label):
            continue
        targets.append(strip_markdown_link_target(match.group(1)))
    return targets


def validate_wiki(base: Path, cfg: dict[str, Any] | None = None) -> list[str]:
    wiki = base / "wiki"
    errors: list[str] = []
    index = wiki / "index.md"
    pages = list(wiki.rglob("*.md"))
    if not index.exists():
        errors.append("缺少 wiki/index.md")
    elif cfg:
        index_text = index.read_text(encoding="utf-8")
        headings = re.findall(r"^##\s+(.+?)\s*$", index_text, flags=re.MULTILINE)
        for chapter in cfg.get("chapters", []):
            if chapter not in headings:
                errors.append(f"wiki/index.md：缺少报告章节分组：{chapter}")
        indexed_pages = set()
        for link in markdown_links(index):
            resolved = resolve_local_markdown_path(link, index)
            if resolved is None:
                continue
            try:
                indexed_pages.add(resolved.relative_to(wiki.resolve()).as_posix())
            except ValueError:
                continue
        for page in pages:
            relative = page.relative_to(wiki).as_posix()
            if relative not in {"README.md", "index.md", "log.md"} and relative not in indexed_pages:
                errors.append(f"wiki/index.md：专题页面尚未加入索引：{relative}")
    for page in pages:
        for link in markdown_links(page):
            resolved = resolve_local_markdown_path(link, page)
            if resolved is not None and not resolved.exists():
                errors.append(f"{page.relative_to(wiki).as_posix()}：链接目标不存在：{link}")
    return errors
