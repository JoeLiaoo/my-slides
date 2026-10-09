"""Offline chart and icon rendering plus dependency setup."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


def renderer_home() -> Path:
    override = os.environ.get("MY_SLIDES_RENDERER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "MySlides" / "renderer"
    return Path.home() / ".local" / "share" / "my-slides" / "renderer"


def renderer_status() -> dict[str, Any]:
    node = shutil.which("node")
    npm = shutil.which("npm")
    home = renderer_home()
    packages: dict[str, str | None] = {}
    for package in ("echarts", "lucide-static"):
        metadata = home / "node_modules" / package / "package.json"
        if metadata.exists():
            packages[package] = json.loads(metadata.read_text(encoding="utf-8")).get("version")
        else:
            packages[package] = None
    return {"node": node, "npm": npm, "home": str(home), "packages": packages,
            "ready": bool(node and npm and packages == {"echarts": "6.1.0", "lucide-static": "1.52.0"})}


def install_renderers() -> dict[str, Any]:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise ValueError("安装图表和图标渲染器需要 Node.js 与 npm；安装 Node.js 后重试 my-slides renderer install")
    existing = renderer_status()
    if existing["ready"]:
        return existing
    home = renderer_home()
    resources = Path(__file__).parent / "renderer"
    home.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        source = resources / name
        if not source.exists():
            raise ValueError(f"安装包缺少渲染依赖清单：{source.name}")
        (home / name).write_bytes(source.read_bytes())
    cache = home / ".npm-cache"
    result = subprocess.run([npm, "ci", "--prefix", str(home), "--cache", str(cache), "--ignore-scripts", "--no-audit", "--no-fund"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError("npm 安装渲染依赖失败：" + (result.stderr or result.stdout).strip())
    status = renderer_status()
    if not status["ready"]:
        raise ValueError(f"渲染器版本不符合锁定要求：{status['packages']}")
    return status


def _is_js_parseable_date(value: str) -> bool:
    """Approximate JS Date.parse for the ISO / common forms used in charts."""
    text = value.strip()
    if not text:
        return False
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            datetime.fromisoformat(candidate)
            return True
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def validate_chart_spec(spec: dict[str, Any]) -> None:
    kind = spec.get("type")
    supported = {"bar", "dot", "line", "multi-line", "scatter", "time-scatter", "stacked-bar", "waterfall"}
    if kind not in supported:
        raise ValueError(f"不支持的图表类型：{kind}")
    def values_ok(values: Any, label: str) -> None:
        if not isinstance(values, list) or not values:
            raise ValueError(f"{label} 必须是非空数组")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not __import__("math").isfinite(value) for value in values):
            raise ValueError(f"{label} 必须全部为有限数值；缺失值不能按 0 绘制")
    width = spec.get("width")
    height = spec.get("height")
    effective_width = width if isinstance(width, int) and not isinstance(width, bool) else 1100
    effective_height = height if isinstance(height, int) and not isinstance(height, bool) else 560
    if effective_width < 320 or effective_width > 1800 or effective_height < 240 or effective_height > 1000:
        raise ValueError("图表宽高超出允许范围（宽 320–1800，高 240–1000）")
    if kind in {"bar", "dot", "line", "waterfall"}:
        categories = spec.get("categories")
        if not isinstance(categories, list) or not categories or any(not isinstance(v, str) or not v.strip() for v in categories):
            raise ValueError("categories 必须是非空文本数组")
        values_ok(spec.get("values"), "values")
        if len(categories) != len(spec["values"]):
            raise ValueError("categories 与 values 长度必须一致")
    if kind in {"multi-line", "stacked-bar"}:
        categories, series = spec.get("categories"), spec.get("series")
        if not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
            raise ValueError("categories 和 series 必须为非空数组")
        unit = spec.get("unit", "")
        for item in series:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError("每个 series 都必须有名称")
            values_ok(item.get("values"), f"series {item.get('name')}")
            if len(item["values"]) != len(categories):
                raise ValueError(f"series {item['name']} 与 categories 长度不一致")
            if item.get("unit", unit) != unit:
                raise ValueError(f"series {item['name']} 单位与图表单位不一致")
    if kind in {"scatter", "time-scatter"}:
        points = spec.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError("points 必须为非空数组")
        if not isinstance(spec.get("xUnit"), str) or not isinstance(spec.get("yUnit"), str):
            raise ValueError("散点图必须分别明确 xUnit 和 yUnit")
        for point in points:
            if not isinstance(point, dict):
                raise ValueError("散点数据必须为对象数组")
            if kind == "scatter":
                values_ok([point.get("x"), point.get("y")], "散点坐标")
            else:
                date = point.get("date")
                y_value = point.get("y")
                if (
                    not isinstance(date, str)
                    or not _is_js_parseable_date(date)
                    or isinstance(y_value, bool)
                    or not isinstance(y_value, (int, float))
                    or not __import__("math").isfinite(y_value)
                ):
                    raise ValueError("时间散点需要可解析的 date 和有限数值 y")
    if kind == "waterfall":
        totals = spec.get("totals", [])
        if not isinstance(totals, list) or any(not isinstance(i, int) or i < 0 or i >= len(spec["values"]) for i in totals):
            raise ValueError("waterfall totals 必须为有效的数据索引")


def sanitize_svg(svg: str, name: str) -> str:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"{name} 渲染结果不是有效 SVG：{exc}") from exc
    allowed = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs", "clipPath", "linearGradient", "radialGradient", "stop", "pattern", "mask", "filter", "feGaussianBlur", "feOffset", "feBlend", "title", "desc", "style"}
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag not in allowed:
            raise ValueError(f"{name} SVG 包含不允许的元素：{tag}")
        if tag == "style" and re.search(r"@import|url\s*\(\s*['\"]?(?!#)", element.text or "", flags=re.I):
            raise ValueError(f"{name} SVG 样式包含外部导入或 URL")
        for key, value in element.attrib.items():
            attr = key.split("}")[-1].lower()
            if attr.startswith("on") or (attr in {"href", "src"} and not value.startswith("#")):
                raise ValueError(f"{name} SVG 包含不安全属性：{attr}")
            if "javascript:" in value.lower() or "@import" in value.lower():
                raise ValueError(f"{name} SVG 包含不安全内容")
            if attr == "style" and re.search(r"url\s*\(\s*['\"]?(?!#)", value, flags=re.I):
                raise ValueError(f"{name} SVG 样式包含外部 URL")
    return svg


def render_assets(assets: list[dict[str, Any]], brand_color: str = "#A6192E") -> dict[str, str]:
    if not assets:
        return {}
    status = renderer_status()
    if not status["ready"]:
        raise ValueError("本地渲染器未就绪，请运行 my-slides renderer install；状态：" + json.dumps(status, ensure_ascii=False))
    script = Path(__file__).parent / "renderer" / "render.mjs"
    env = os.environ.copy()
    env["MY_SLIDES_RENDERER_HOME"] = str(renderer_home())
    result = subprocess.run([status["node"], str(script)], input=json.dumps({"assets": assets, "brandColor": brand_color}, ensure_ascii=False),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if result.returncode:
        raise ValueError("本地 SVG 渲染失败：" + (result.stderr or result.stdout).strip())
    try:
        rendered = json.loads(result.stdout).get("rendered", {})
    except json.JSONDecodeError as exc:
        raise ValueError("本地渲染器返回了无效结果") from exc
    if set(rendered) != {asset["id"] for asset in assets}:
        raise ValueError("本地渲染器返回结果不完整")
    return {key: sanitize_svg(value, key) for key, value in rendered.items()}


def renderer_notices() -> str:
    home = renderer_home() / "node_modules"
    notices = []
    for package, version, license_name, source in (
        ("echarts", "6.1.0", "Apache-2.0", "https://github.com/apache/echarts"),
        ("lucide-static", "1.52.0", "ISC", "https://github.com/lucide-icons/lucide"),
    ):
        text = (home / package / "LICENSE").read_text(encoding="utf-8")
        notices.append(f"<h3>{html.escape(package)} {version} · {license_name}</h3><p><a href=\"{source}\">{source}</a></p><pre>{html.escape(text)}</pre>")
    return "\n".join(notices)
