"""把锁定的 html-slides 样式打进安装包，并生成统一的页面外壳。

单页预览和整套演示文稿共用这里的 CSS、字体和切页规则。
原始样式在 slides_theme/upstream，本地改动只在 adapt.css。
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from importlib.resources import files
from typing import Any

# 首版只支持这一套浅色主题。
THEME_NAME = "editorial-light"
SHELL_VERSION = "1"
FONT_POLICY = "system-cjk-v1"
ADAPTATION_VERSION = "2"
UPSTREAM_COMMIT = "d8289f4c317905cc5d0ca265d32b791e6cb387b7"

_ASSET_ORDER = (
    "upstream/viewport-base.css",
    "upstream/components.css",
    "upstream/editorial-light.css",
    "upstream/LICENSE",
    "adapt.css",
)


def _resource(relative: str) -> bytes:
    """从安装包读取样式，不访问网络，也不依赖源码目录。"""
    resource = files("my_slides").joinpath("slides_theme")
    for part in relative.split("/"):
        resource = resource.joinpath(part)
    return resource.read_bytes()


def _text(relative: str) -> str:
    return _resource(relative).decode("utf-8")


def load_manifest() -> dict[str, Any]:
    return json.loads(_text("manifest.json"))


def verify_assets() -> list[str]:
    """核对清单里的提交号和每个文件的 SHA-256。"""
    manifest = load_manifest()
    errors: list[str] = []
    upstream = manifest.get("upstream") or {}
    if upstream.get("commit") != UPSTREAM_COMMIT:
        errors.append("上游提交号与代码不一致")
    if manifest.get("theme") != THEME_NAME:
        errors.append("主题名称与代码不一致")
    recorded = manifest.get("files") or {}
    for relative in _ASSET_ORDER:
        info = recorded.get(relative) or {}
        digest = hashlib.sha256(_resource(relative)).hexdigest()
        if info.get("sha256") != digest:
            errors.append(f"{relative} 的 SHA-256 与清单不一致")
    return errors


def asset_digest() -> str:
    """样式文件变化后，这个摘要会变，旧页面缓存随之失效。"""
    hasher = hashlib.sha256()
    for relative in _ASSET_ORDER:
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(_resource(relative))
    hasher.update(SHELL_VERSION.encode("utf-8"))
    hasher.update(FONT_POLICY.encode("utf-8"))
    hasher.update(ADAPTATION_VERSION.encode("utf-8"))
    return hasher.hexdigest()


def theme_cache_fields() -> dict[str, str]:
    return {
        "name": THEME_NAME,
        "asset_digest": asset_digest(),
        "shell_version": SHELL_VERSION,
        "font_policy": FONT_POLICY,
        "adaptation_version": ADAPTATION_VERSION,
    }


def shell_fingerprint() -> str:
    from .dependencies import fingerprint_json

    return fingerprint_json(theme_cache_fields())


def _strip_external_fonts(css: str) -> str:
    """去掉主题里的 Google Fonts。字体改由适配层的系统字体栈提供。"""
    return re.sub(r"@import\s+url\([^)]*\)\s*;", "/* external font import removed */", css)


def shell_css(brand_color: str) -> str:
    errors = verify_assets()
    if errors:
        raise ValueError("幻灯片样式资产与清单不一致：" + "；".join(errors))
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        raise ValueError("brand_color 必须是 #RRGGBB")
    css = "\n".join(
        [
            _text("upstream/viewport-base.css"),
            _text("upstream/components.css"),
            _strip_external_fonts(_text("upstream/editorial-light.css")),
            _text("adapt.css"),
            f":root {{ --brand: {brand_color}; --accent-blue: var(--brand); }}",
        ]
    )
    if re.search(r"@import|fonts\.googleapis|fonts\.gstatic|fontshare", css, flags=re.I):
        raise ValueError("外壳样式仍包含外部字体")
    return css


def wrap_rendered_asset(kind: str, svg: str) -> str:
    """图表和小图标分开包一层，避免同一条 SVG 规则把图标压扁。"""
    if kind == "chart":
        return f'<div class="mls-chart">{svg}</div>'
    return f'<span class="mls-icon">{svg}</span>'


def _ensure_first_active(sections: list[str]) -> list[str]:
    if not sections:
        return sections

    first = re.sub(
        r'\bclass=(["\'])([^"\']*\bslide\b[^"\']*)\1',
        _activate_class,
        sections[0],
        count=1,
    )
    return [first, *sections[1:]]


def _activate_class(match: re.Match[str]) -> str:
    classes = match.group(2).split()
    if "active" not in classes:
        classes.append("active")
    quote = match.group(1)
    return f'class={quote}{" ".join(classes)}{quote}'


def render_document(
    sections: list[str],
    css_blocks: list[str],
    *,
    title: str,
    brand_color: str,
    has_assets: bool,
    kind: str = "deck",
) -> str:
    """生成单页预览或整套演示文稿。两者的样式和切页规则相同。"""
    if kind not in {"deck", "preview"}:
        raise ValueError("文档类型必须是 deck 或 preview")
    prepared = _ensure_first_active(sections)
    css = shell_css(brand_color) + "\n" + "".join(css_blocks)
    design_meta = f"bluedusk/html-slides@{UPSTREAM_COMMIT} (MIT); theme={THEME_NAME}; shell={SHELL_VERSION}"
    renderer_meta = (
        "ECharts 6.1.0 (Apache-2.0); Lucide Static 1.52.0 (ISC)"
        if has_assets
        else "Native HTML/CSS only"
    )
    notices = (
        '<details id="third-party-notices"><summary>第三方许可与来源</summary>'
        f"<h3>html-slides · MIT</h3><p>{html.escape(design_meta)}</p>"
        f"<pre>{html.escape(_text('upstream/LICENSE'))}</pre>"
    )
    if has_assets:
        from .cli import renderer_notices

        notices += renderer_notices()
    notices += "</details>"
    body = "".join(prepared)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="my-slides"><meta name="my-slides-kind" content="{html.escape(kind, quote=True)}"><meta name="my-slides-theme" content="{THEME_NAME}"><meta name="my-slides-shell" content="{SHELL_VERSION}"><meta name="my-slides-fonts" content="{FONT_POLICY}"><meta name="my-slides-renderers" content="{html.escape(renderer_meta, quote=True)}"><meta name="design-reference" content="{html.escape(design_meta, quote=True)}"><title>{html.escape(title)}</title>
<style>
{css}
</style></head><body>
<div class="deck" id="deck" data-deck-stage>{body}</div>
<nav id="controls" aria-label="Slides navigation"><button type="button" id="prevSlide">上一页</button><span id="pageCount"></span><button type="button" id="nextSlide">下一页</button></nav>
{notices}
<script>
const pages=Array.from(document.querySelectorAll(".slide"));
let current=Math.max(0, pages.findIndex((page)=>page.classList.contains("active")));
function goTo(n){{current=Math.max(0,Math.min(pages.length-1,n));pages.forEach((page,index)=>page.classList.toggle("active",index===current));const count=document.getElementById("pageCount");if(count)count.textContent=(current+1)+" / "+pages.length}}
function next(){{goTo(current+1)}}function prev(){{goTo(current-1)}}
document.getElementById("prevSlide").addEventListener("click",prev);
document.getElementById("nextSlide").addEventListener("click",next);
addEventListener("keydown",event=>{{if(["ArrowRight","PageDown"," "].includes(event.key)){{event.preventDefault();next()}}if(["ArrowLeft","PageUp"].includes(event.key)){{event.preventDefault();prev()}}}});
const stage=document.getElementById("deck");
let touchX=0;
stage.addEventListener("touchstart",event=>{{touchX=event.changedTouches[0].clientX}},{{passive:true}});
stage.addEventListener("touchend",event=>{{const delta=event.changedTouches[0].clientX-touchX;if(Math.abs(delta)>50)(delta<0?next:prev)()}},{{passive:true}});
goTo(current<0?0:current);
</script></body></html>
"""
