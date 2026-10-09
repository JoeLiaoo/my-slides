"""Safe parsing and CSS checks for unit HTML fragments."""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any


def extract_approved_icons(icon_section: str) -> set[str]:
    """Parse Spec「图标需求」into Lucide kebab-case names.

    Only an entire section that is exactly「无」means no icons. List items
    (``- name``) are preferred; comma-separated tokens are also accepted.
    """
    text = icon_section.strip()
    if not text or text == "无":
        return set()
    icons: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        list_match = re.match(
            r"^[-*+]\s+`?([a-z0-9]+(?:-[a-z0-9]+)*)`?(?:\s|[（(,，]|$)",
            stripped,
        )
        if list_match:
            icons.add(list_match.group(1))
            continue
        if stripped.startswith(("-", "*", "+")):
            continue
        for token in re.split(r"[,，、\s]+", stripped):
            token = token.strip().strip("`")
            # Drop Chinese parenthetical notes glued to the name.
            token = re.split(r"[（(]", token, maxsplit=1)[0].strip()
            if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", token):
                icons.add(token)
    return icons


def validate_scoped_css(css: str, *, label: str) -> list[str]:
    """Reject CSS that would escape an @scope wrapper via unbalanced braces."""
    depth = 0
    index = 0
    length = len(css)
    while index < length:
        char = css[index]
        if char == "/" and index + 1 < length and css[index + 1] == "*":
            end = css.find("*/", index + 2)
            if end < 0:
                return [f"{label}：CSS 注释未闭合"]
            index = end + 2
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            while index < length:
                if css[index] == "\\":
                    index += 2
                    continue
                if css[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return [f"{label}：CSS 括号不配对，会跳出章节 @scope 作用域"]
        index += 1
    if depth != 0:
        return [f"{label}：CSS 括号不配对，会跳出章节 @scope 作用域"]
    return []


class SlideFragmentParser(HTMLParser):
    """Collect slide sections from one agent-produced chapter fragment."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    # Whitelist: presentation HTML + common SVG. Dangerous tags are rejected outright.
    ALLOWED_TAGS = frozenset({
        "section", "div", "span", "header", "footer", "main", "article", "aside", "nav",
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "dl", "dt", "dd",
        "a", "strong", "em", "b", "i", "u", "s", "small", "mark", "abbr", "time", "sub", "sup",
        "code", "pre", "blockquote", "q", "cite", "figure", "figcaption",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
        "img", "picture", "source",
        "svg", "g", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse",
        "text", "tspan", "defs", "use", "symbol", "clippath", "lineargradient", "radialgradient",
        "stop", "title", "desc", "mask", "pattern", "marker",
        "script", "style",
    })
    FORBIDDEN_TAGS = frozenset({
        "meta", "form", "animate", "set", "animatetransform", "animatemotion",
        "iframe", "object", "embed", "base", "link", "input", "button", "textarea", "select",
        "option", "applet", "frame", "frameset", "video", "audio", "portal", "foreignobject",
    })
    ALLOWED_ATTRS = frozenset({
        "id", "class", "lang", "dir", "title", "role", "tabindex", "hidden", "type",
        "href", "alt", "width", "height", "loading", "decoding", "colspan", "rowspan", "scope", "span",
        "viewbox", "xmlns", "xmlns:xlink", "fill", "stroke", "stroke-width", "stroke-linecap",
        "stroke-linejoin", "opacity", "transform", "d", "cx", "cy", "r", "rx", "ry",
        "x", "y", "x1", "y1", "x2", "y2", "points", "preserveaspectratio", "clip-path",
        "fill-rule", "clip-rule", "font-size", "font-family", "font-weight", "text-anchor",
        "dominant-baseline", "gradientunits", "gradienttransform", "offset", "stop-color",
        "stop-opacity", "xlink:href", "href", "aria-hidden", "aria-label", "aria-labelledby",
        "focusable", "overflow", "vector-effect", "style",
    })
    URL_ATTRS = frozenset({
        "href", "action", "formaction", "xlink:href", "poster", "background", "to", "values", "from",
    })
    SRC_ATTRS = frozenset({"src", "srcset"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.slides: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.css: list[str] = []
        self.active: dict[str, Any] | None = None
        self.stack: list[str] = []
        self.style = False
        self.note_script = False
        self.asset_script: str | None = None
        self.asset_data: list[str] = []
        self._skip_depth = 0

    @staticmethod
    def render_tag(tag: str, attrs: list[tuple[str, str | None]], closed: bool = False) -> str:
        rendered = "".join(f' {name}="{html.escape(value or "", quote=True)}"' for name, value in attrs)
        return f"<{tag}{rendered}{' /' if closed else ''}>"

    @staticmethod
    def normalize_url_candidate(value: str) -> str:
        """Decode entities, strip whitespace/controls, lowercase — for protocol checks."""
        decoded = html.unescape(value or "")
        return re.sub(r"[\s\x00-\x1f\x7f]+", "", decoded).lower()

    @classmethod
    def is_allowed_url(cls, value: str) -> bool:
        normalized = cls.normalize_url_candidate(value)
        if not normalized:
            return True
        if normalized.startswith("#"):
            return True
        if normalized.startswith("//"):
            return False
        if normalized.startswith("https:") or normalized.startswith("mailto:"):
            return True
        # Block any other scheme (javascript:, data:, http:, vbscript:, …).
        if re.match(r"^[a-z][a-z0-9+.-]*:", normalized):
            return False
        return True

    def sanitize_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        cleaned: list[tuple[str, str | None]] = []
        for name, value in attrs:
            lower = name.lower()
            if lower.startswith("on"):
                self.errors.append(f"章节片段不允许内联事件属性：{name}")
                continue
            if lower.startswith("data-") or lower.startswith("aria-"):
                cleaned.append((name, value))
                continue
            if lower in self.SRC_ATTRS:
                if value and not value.strip().lower().startswith("data:"):
                    self.errors.append(f"章节片段包含外部资源：{value}")
                    continue
                cleaned.append((name, value))
                continue
            if lower in self.URL_ATTRS:
                if value and not self.is_allowed_url(value):
                    self.errors.append(f"章节片段包含不安全链接属性 {name}：{value}")
                    continue
                cleaned.append((name, value))
                continue
            if lower == "style" and value and re.search(r"url\s*\(|@import", value, flags=re.I):
                self.errors.append("章节片段的 style 属性包含外部导入或 URL")
                continue
            if lower not in self.ALLOWED_ATTRS:
                self.errors.append(f"章节片段不允许属性：{name}")
                continue
            cleaned.append((name, value))
        return cleaned

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            if lower_tag not in self.VOID:
                self._skip_depth += 1
            return
        attr = {name: value for name, value in attrs}
        classes = (attr.get("class") or "").split()
        if lower_tag in self.FORBIDDEN_TAGS or lower_tag not in self.ALLOWED_TAGS:
            self.errors.append(f"章节片段不允许使用 <{tag}>")
            if lower_tag not in self.VOID:
                self._skip_depth = 1
            return
        if lower_tag == "script":
            allowed = {"slide-notes", "mls-echarts-spec", "mls-lucide-spec"}
            if attr.get("type") != "application/json" or not (allowed & set(classes)):
                self.errors.append("章节片段包含脚本；只允许 slide-notes、mls-echarts-spec 或 mls-lucide-spec JSON 标记")
                self._skip_depth = 1
                return
            if "slide-notes" in classes:
                if self.active and self.active["has_notes"]:
                    self.errors.append("每张 slide 只能包含一个 slide-notes 对象")
                if self.active:
                    self.active["has_notes"] = True
                self.note_script = True
            asset_classes = {"mls-echarts-spec", "mls-lucide-spec"} & set(classes)
            if asset_classes:
                if len(asset_classes) != 1:
                    self.errors.append("每个渲染标记只能使用一种资产类型")
                if not self.active:
                    self.errors.append("ECharts/Lucide 标记必须位于 slide 内")
                self.asset_script = next(iter(asset_classes))
                self.asset_data = []
        safe_attrs = self.sanitize_attrs(lower_tag, attrs)
        if lower_tag == "style":
            self.style = True
        is_slide = "slide" in classes
        if is_slide:
            if self.active:
                self.errors.append("章节片段中不允许嵌套 slide")
            else:
                if lower_tag not in {"section", "div"}:
                    self.errors.append("slide 根元素必须是 <section> 或 <div>")
                slide_id = attr.get("id", "") or ""
                self.active = {"html": [], "notes": [], "assets": [], "has_notes": False, "id": slide_id,
                               "role": attr.get("data-page-role", "") or ""}
                self.stack = []
        if self.active:
            self.active["html"].append(self.render_tag(tag, safe_attrs))
            if lower_tag not in self.VOID:
                self.stack.append(lower_tag)
        if lower_tag in self.VOID and self.active and is_slide:
            self.errors.append("slide 根元素必须是 section 或 div")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            return
        if lower_tag in self.FORBIDDEN_TAGS or lower_tag not in self.ALLOWED_TAGS:
            self.errors.append(f"章节片段不允许使用 <{tag}>")
            return
        safe_attrs = self.sanitize_attrs(lower_tag, attrs)
        rendered = self.render_tag(tag, safe_attrs, closed=True)
        if self.active:
            self.active["html"].append(rendered)
        elif lower_tag == "style":
            self.errors.append("style 元素不能为空")

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if self._skip_depth:
            if lower_tag not in self.VOID:
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        if lower_tag == "style":
            self.style = False
        if lower_tag == "script":
            self.note_script = False
            if self.asset_script:
                try:
                    spec = json.loads("".join(self.asset_data))
                    if not isinstance(spec, dict):
                        raise ValueError("JSON 必须是对象")
                    kind = "chart" if self.asset_script == "mls-echarts-spec" else "icon"
                    if self.active:
                        self.active["assets"].append({"kind": kind, "spec": spec})
                except (json.JSONDecodeError, ValueError) as exc:
                    self.errors.append(f"{self.asset_script} JSON 无效：{exc}")
                self.asset_script = None
                self.asset_data = []
        if self.active:
            self.active["html"].append(f"</{tag}>")
            if self.stack and self.stack[-1] == lower_tag:
                self.stack.pop()
            elif lower_tag in self.stack:
                self.errors.append(f"HTML 标签嵌套顺序错误：</{tag}>")
                self.stack = self.stack[:self.stack.index(lower_tag)]
            if not self.stack:
                slide = self.active
                self.slides.append(slide)
                self.active = None
                self.note_script = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self.style:
            self.css.append(data)
        if self.active:
            self.active["html"].append(data)
            if self.note_script:
                self.active["notes"].append(data)
            if self.asset_script:
                self.asset_data.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth:
            return
        raw = f"&{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_charref(self, name: str) -> None:
        if self._skip_depth:
            return
        raw = f"&#{name};"
        if self.active:
            self.active["html"].append(raw)
            if self.note_script:
                self.active["notes"].append(raw)
            if self.asset_script:
                self.asset_data.append(raw)

    def handle_comment(self, data: str) -> None:
        if self._skip_depth:
            return
        if self.active:
            self.active["html"].append(f"<!--{data}-->")
