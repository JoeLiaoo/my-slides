"""v2 per-unit slide compile, cache, and deck assembly (Phase 5).

Charts/icons may only come from the unit's own approved Spec (P3-9).
Delivery writes temp files then renames (P3-7).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from .slide_fragments import (
    SlideFragmentParser,
    extract_approved_icons,
    validate_scoped_css,
)
from .rendering import render_assets, renderer_status, validate_chart_spec
from .dependencies import fingerprint_file, fingerprint_json
from .state import read_unit_state, refresh_unit_currency, write_unit_state
from .theme import render_document, shell_fingerprint, theme_cache_fields, wrap_rendered_asset
from .unit_workflow import resolve_unit_selection
from .units import Unit, UnitsError, load_units_manifest, unit_paths


CACHE_DIR = ".state/cache"


def _atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(content, str):
        tmp.write_text(content, encoding="utf-8")
    else:
        tmp.write_bytes(content)
    tmp.replace(path)


def _cache_path(base: Path, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return base / CACHE_DIR / digest[:2] / f"{digest}.html"


def approved_assets_from_spec(spec_text: str) -> tuple[set[str], set[str]]:
    charts: set[str] = set()
    icons: set[str] = set()
    for raw in re.findall(r"```echarts-spec\s*\n(.*?)\n```", spec_text, flags=re.DOTALL):
        try:
            charts.add(json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        except json.JSONDecodeError:
            pass
    for section in re.findall(r"^###\s+图标需求\s*$\s*(.*?)(?=^###\s|^##\s|\Z)", spec_text, flags=re.MULTILINE | re.DOTALL):
        icons.update(extract_approved_icons(section))
    return charts, icons


def compute_unit_cache_key(
    base: Path,
    unit: Unit,
    *,
    brand_color: str,
) -> tuple[str | None, list[str], dict[str, Any] | None]:
    """Compute the full page cache key for current inputs (brand/renderer included).

    Returns ``(cache_key, errors, context)`` where context carries parsed slide data
    for compile_unit_page when key computation succeeds.
    """
    paths = unit_paths(base, unit.id)
    errors: list[str] = []
    if not paths.page.is_file():
        return None, [f"{unit.id}：缺少 slides/pages/{unit.id}.html"], None
    if not paths.spec.is_file():
        return None, [f"{unit.id}：缺少 Spec"], None

    spec_text = paths.spec.read_text(encoding="utf-8")
    approved_charts, approved_icons = approved_assets_from_spec(spec_text)

    parser = SlideFragmentParser()
    try:
        parser.feed(paths.page.read_text(encoding="utf-8"))
        parser.close()
    except Exception as exc:  # noqa: BLE001
        return None, [f"{unit.id}：HTML 解析失败：{exc}"], None
    errors.extend(f"{unit.id}：{issue}" for issue in parser.errors)
    if parser.active:
        errors.append(f"{unit.id}：slide 标签未闭合")
    if len(parser.slides) != 1:
        errors.append(f"{unit.id}：每个单元 HTML 必须恰好一页（当前 {len(parser.slides)}）")
    if errors:
        return None, errors, None

    slide = parser.slides[0]
    if (slide.get("role") or unit.role) and (slide.get("role") or unit.role) != unit.role:
        role = slide.get("role") or unit.role
        if role != unit.role:
            errors.append(f"{unit.id}：data-page-role 与 units.json 不一致")
    css = "".join(parser.css)
    if re.search(r"@import|url\s*\(", css, flags=re.I):
        errors.append(f"{unit.id}：样式包含外部导入或 URL")
    errors.extend(validate_scoped_css(css, label=unit.id))
    if not slide["has_notes"]:
        errors.append(f"{unit.id}：需要 slide-notes JSON 对象")
    else:
        try:
            note = json.loads("".join(slide["notes"]))
            if not isinstance(note, dict):
                errors.append(f"{unit.id}：slide-notes 必须是 JSON 对象")
        except json.JSONDecodeError:
            errors.append(f"{unit.id}：slide-notes JSON 无效")

    assets_to_render: list[dict[str, Any]] = []
    for asset in slide["assets"]:
        try:
            if asset["kind"] == "chart":
                validate_chart_spec(asset["spec"])
                canonical = json.dumps(asset["spec"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if canonical not in approved_charts:
                    raise ValueError("图表数据必须与本单元已批准 Spec 中的 echarts-spec 完全一致（禁止借用其他单元）")
            else:
                icon_name = asset["spec"].get("name", "")
                if not isinstance(icon_name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", icon_name):
                    raise ValueError("Lucide 图标名称必须使用 kebab-case")
                if icon_name not in approved_icons:
                    raise ValueError(f"图标 {icon_name} 未在本单元 Spec 的图标需求中声明")
            asset["id"] = f"{unit.id}-asset-{len(assets_to_render)}"
            assets_to_render.append(asset)
        except ValueError as exc:
            errors.append(f"{unit.id}：{exc}")
    if errors:
        return None, errors, None

    cache_key = fingerprint_json(
        {
            "unit": unit.id,
            "html": fingerprint_file(paths.page),
            "spec": fingerprint_file(paths.spec),
            "css": css,
            "brand": brand_color,
            "renderer": renderer_status().get("packages"),
            "theme": theme_cache_fields(),
            "assets": [asset["spec"] for asset in assets_to_render],
        }
    )
    return cache_key, [], {
        "paths": paths,
        "slide": slide,
        "css": css,
        "assets_to_render": assets_to_render,
    }


def compile_unit_page(
    base: Path,
    unit: Unit,
    *,
    brand_color: str,
    write_preview: bool = True,
) -> tuple[str | None, list[str]]:
    """Compile one unit HTML page with assets; optional preview write."""
    state = refresh_unit_currency(base, unit, project_root=base.parent)
    if not state["spec"]["current"]:
        return None, [f"{unit.id}：Spec 未批准或已失效，无法构建"]

    cache_key, errors, ctx = compute_unit_cache_key(base, unit, brand_color=brand_color)
    if errors or cache_key is None or ctx is None:
        return None, errors

    paths = ctx["paths"]
    slide = ctx["slide"]
    css = ctx["css"]
    assets_to_render = ctx["assets_to_render"]
    cached = _cache_path(base, cache_key)
    if cached.is_file():
        payload = json.loads(cached.read_text(encoding="utf-8"))
    else:
        try:
            rendered = render_assets(assets_to_render, brand_color) if assets_to_render else {}
        except (OSError, ValueError) as exc:
            return None, [str(exc)]
        source = "".join(slide["html"])
        asset_index = 0
        marker_pattern = re.compile(
            r'<script\b(?=[^>]*\btype="application/json")'
            r'(?=[^>]*\bclass="(?:[^"]*\s)?(?:mls-echarts-spec|mls-lucide-spec)(?:\s[^"]*)?")'
            r"[^>]*>.*?</script>",
            flags=re.DOTALL,
        )

        def replace_asset(_match: re.Match[str]) -> str:
            nonlocal asset_index
            asset = assets_to_render[asset_index]
            asset_index += 1
            return wrap_rendered_asset(asset["kind"], rendered[asset["id"]])

        if assets_to_render:
            source = marker_pattern.sub(replace_asset, source)
            if asset_index != len(assets_to_render):
                return None, [f"{unit.id}：渲染标记数量不一致"]
        if "data-unit-id=" not in source:
            source = re.sub(
                r"(<(?:section|div)\b[^>]*\bclass=[\"'][^\"']*\bslide\b[^\"']*[\"'])",
                rf'\1 data-unit-id="{html.escape(unit.id, quote=True)}"',
                source,
                count=1,
                flags=re.I,
            )
        scope_css = f'@scope ([data-unit-id="{unit.id}"]) {{\n{css}\n}}' if css else ""
        payload = {
            "unit_id": unit.id,
            "role": unit.role,
            "html": source,
            "css": scope_css,
            "cache_key": cache_key,
        }
        _atomic_write(cached, json.dumps(payload, ensure_ascii=False))

    if write_preview:
        preview = render_document(
            [payload["html"]],
            [payload.get("css") or ""],
            title=unit.id,
            brand_color=brand_color,
            has_assets="mls-chart" in payload["html"] or "mls-icon" in payload["html"] or "<svg" in payload["html"],
            kind="preview",
        )
        _atomic_write(paths.preview, preview)

    state["html"] = {
        "content_sha256": fingerprint_file(paths.page),
        "spec_sha256": state["spec"]["approved_sha256"],
        "build_sha256": fingerprint_file(paths.page),
        "cache_key": cache_key,
        "shell_fingerprint": shell_fingerprint(),
        "current": True,
    }
    state["reasons"] = [r for r in state.get("reasons", []) if "HTML" not in r]
    write_unit_state(base, unit.id, state)
    return payload["html"], []


def build_units_deck(
    base: Path,
    cfg: dict[str, Any],
    *,
    unit_ids: list[str] | None = None,
    changed: bool = False,
    all_units: bool = False,
    write: bool = True,
) -> tuple[Path | None, list[str], dict[str, Any]]:
    """Build selected unit pages and optionally assemble formal index.html."""
    units = resolve_unit_selection(
        base, cfg, unit_ids=unit_ids, changed=changed, all_units=all_units or not (unit_ids or changed)
    )
    all_manifest, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        return None, errors, {}
    brand_color = cfg.get("brand_color", "#A6192E")
    if not isinstance(brand_color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        return None, ["project.yaml 的 brand_color 必须是 #RRGGBB 格式"], {}

    plan = {"rebuild": [], "reused": [], "blocked": [], "reasons": {}}
    page_payloads: dict[str, dict[str, Any]] = {}
    build_errors: list[str] = []

    # Compile requested units.
    for unit in units:
        html_fragment, unit_errors = compile_unit_page(base, unit, brand_color=brand_color, write_preview=True)
        if unit_errors:
            build_errors.extend(unit_errors)
            plan["blocked"].append(unit.id)
            plan["reasons"][unit.id] = unit_errors
            continue
        plan["rebuild"].append(unit.id)
        # Reload from cache file written by compile
        state = read_unit_state(base, unit.id)
        cache_key = state["html"].get("cache_key")
        if cache_key:
            cached = _cache_path(base, cache_key)
            page_payloads[unit.id] = json.loads(cached.read_text(encoding="utf-8"))

    if build_errors and not all_units and unit_ids:
        # Previews may exist; do not overwrite formal deck when any selected unit failed.
        return None, build_errors, plan

    # Assemble only when every manifest unit is buildable/reusable.
    sections: list[str] = []
    css_blocks: list[str] = []
    has_assets = False
    for index, unit in enumerate(all_manifest):
        state = refresh_unit_currency(base, unit, project_root=base.parent)
        if unit.id in page_payloads:
            payload = page_payloads[unit.id]
        else:
            # 按当前 brand/renderer/页面/Spec 重算完整 cache key；不能只看 html.current，
            # 否则改 brand_color 后仍会复用旧配色图标/图表。
            expected_key, key_errors, _ctx = compute_unit_cache_key(
                base, unit, brand_color=brand_color
            )
            expected_cached = _cache_path(base, expected_key) if expected_key and not key_errors else None
            # Spec 刚重新批准时，旧缓存仍然在，但 HTML 还绑着上一版 Spec，不能复用。
            if (
                expected_cached
                and expected_cached.is_file()
                and state["html"]["current"]
                and state["html"].get("cache_key") == expected_key
            ):
                payload = json.loads(expected_cached.read_text(encoding="utf-8"))
                plan["reused"].append(unit.id)
            else:
                payload = None
        if payload is None:
            # Try compile on the fly for --all
            html_fragment, unit_errors = compile_unit_page(base, unit, brand_color=brand_color, write_preview=True)
            if unit_errors:
                build_errors.extend(unit_errors)
                plan["blocked"].append(unit.id)
                plan["reasons"][unit.id] = unit_errors
                continue
            state = read_unit_state(base, unit.id)
            cached = _cache_path(base, state["html"]["cache_key"])
            payload = json.loads(cached.read_text(encoding="utf-8"))
            plan["rebuild"].append(unit.id)
        source = payload["html"]
        # Strip prior indices/ids so rewrite injects exactly one of each (pages may
        # already carry data-unit-id from compile_unit_page).
        source = re.sub(r'\sdata-slide=["\'][^"\']*["\']', "", source, count=1)
        source = re.sub(r'\sdata-unit-id=["\'][^"\']*["\']', "", source, count=1)
        marker = f'data-slide="{index}" data-unit-id="{html.escape(unit.id, quote=True)}"'

        def rewrite_root(match: re.Match[str], *, _index: int = index, _marker: str = marker) -> str:
            classes = [token for token in match.group(1).split() if token != "active"]
            if not _index:
                classes.append("active")
            return f'class="{" ".join(classes)}" {_marker}'

        source = re.sub(r'\bclass=["\']([^"\']*\bslide\b[^"\']*)["\']', rewrite_root, source, count=1)
        sections.append(source)
        if payload.get("css"):
            css_blocks.append(payload["css"])
        if "mls-echarts" in payload["html"] or "<svg" in payload["html"]:
            has_assets = True

    if build_errors or len(sections) != len(all_manifest):
        # Keep prior formal delivery; previews for rebuilt units already saved.
        return None, build_errors or ["尚有单元未就绪，已保存预览但未覆盖正式 index.html"], plan

    output = base / "slides" / "index.html"
    if write:
        document = render_document(
            sections,
            css_blocks,
            title=str(cfg.get("project", "Investment presentation")),
            brand_color=brand_color,
            has_assets=has_assets,
            kind="deck",
        )
        if output.is_file():
            previous = output.read_bytes()
            if previous != document.encode("utf-8"):
                previous_hash = hashlib.sha256(previous).hexdigest()
                archive = base / ".state" / "deliveries" / f"{previous_hash}.html"
                if not archive.is_file():
                    _atomic_write(archive, previous)
        _atomic_write(output, document)
        state_path = base / ".state" / "slides.json"
        _atomic_write(
            state_path,
            json.dumps(
                {
                    "format_version": "v2",
                    "html_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                    "units": [unit.id for unit in all_manifest],
                    "plan": plan,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
    return output if write else None, [], plan
