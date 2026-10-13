"""Headless Chromium validation for the generated standalone deck.

Phase 6: selected pages are activated one-by-one before geometry measurement
so hidden slides' zero-size boxes cannot pass checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

QA_RULES_VERSION = "visual-qa-1"
VIEWPORTS = (("desktop", 1920, 1080), ("mobile-portrait", 390, 844), ("mobile-landscape", 844, 390))


class _DeckSlideParser(HTMLParser):
    """Collect slide elements only, so CSS such as @scope ([data-unit-id=...]) is ignored."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): value or "" for name, value in attrs}
        if "slide" not in attr.get("class", "").split():
            return
        self.slides.append(
            {
                "unit_id": attr.get("data-unit-id", ""),
                "role": attr.get("data-page-role", ""),
            }
        )


def _deck_slides(text: str) -> list[dict[str, str]]:
    parser = _DeckSlideParser()
    parser.feed(text)
    parser.close()
    return parser.slides


# 等有限动画结束再测量。无限循环动画不等待，并设上限，避免检查卡住。
_SETTLE_ANIMATIONS = """async () => {
  const pending = document.getAnimations().filter((animation) => {
    const effect = animation.effect;
    const timing = effect && effect.getTiming ? effect.getTiming() : null;
    return Boolean(timing) && timing.iterations !== Infinity;
  });
  await Promise.race([
    Promise.all(pending.map((animation) => animation.finished.catch(() => undefined))),
    new Promise((resolve) => setTimeout(resolve, 2000))
  ]);
}"""


def grouped_slide_units(slides: list[dict[str, str]]) -> list[tuple[str, int]]:
    """Collapse consecutive pages of the same section into ``(unit_id, page_count)``."""
    groups: list[tuple[str, int]] = []
    for slide in slides:
        unit_id = slide.get("unit_id") or ""
        if not unit_id:
            continue
        if groups and groups[-1][0] == unit_id:
            groups[-1] = (unit_id, groups[-1][1] + 1)
        else:
            groups.append((unit_id, 1))
    return groups


def structural_check_deck(
    path: Path,
    *,
    expected_units: list[str] | None = None,
    expected_page_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Layer-3 lightweight checks that do not need a browser."""
    errors: list[str] = []
    if not path.is_file():
        return {"valid": False, "errors": [f"Slides 文件不存在：{path}"], "measured": False}
    text = path.read_text(encoding="utf-8")
    if '<meta name="generator" content="my-slides">' not in text:
        errors.append("slides/index.html 缺少生成器标记")
    # 只认带 slide 类的页面元素。样式里的 data-unit-id 不是页面。
    slides = _deck_slides(text)
    unit_ids = [slide["unit_id"] for slide in slides if slide["unit_id"]]
    groups = grouped_slide_units(slides)
    if expected_units is not None:
        actual_units = [unit_id for unit_id, _count in groups]
        if actual_units != expected_units:
            errors.append(
                "整套单元集合或顺序与 units.json 不一致："
                f"期望 {expected_units}，实际 {actual_units}"
            )
        elif expected_page_counts is not None:
            for unit_id, count in groups:
                expected = expected_page_counts.get(unit_id)
                if expected is not None and count != expected:
                    errors.append(f"{unit_id}：整套中的页数（{count}）与 Spec 页数（{expected}）不一致")
    covers = sum(1 for slide in slides if slide["role"] == "cover")
    if covers > 1:
        errors.append("整套必须恰好一个 cover 页面")
    if "http://" in text or re.search(r'https://(?!github\.com/)', text):
        # Soft hint — deep offline blocking is done in browser layer.
        pass
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "measured": False,
        "unit_ids": unit_ids,
        "sections": [{"id": unit_id, "pages": count} for unit_id, count in groups],
    }


def check_deck(
    path: Path,
    *,
    unit_ids: list[str] | None = None,
    slide_indexes: list[int] | None = None,
    evidence_dir: Path | None = None,
    spec_hashes: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Browser QA. When unit_ids/slide_indexes given, activate each target before measuring."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("浏览器检查需要 Playwright；安装 my-slides[browser] 后运行 my-slides browser install") from exc

    if not path.exists():
        raise ValueError(f"Slides 文件不存在：{path}")
    # Pillow 仅在 --screenshots（evidence_dir 非空）时用于截图拼图；先于浏览器启动做检查，
    # 让缺包时返回清晰提示，而不是看一段 ImportError 调用栈。
    if evidence_dir is not None:
        try:
            from PIL import Image, ImageDraw  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "生成截图 contact sheet 需要 Pillow；请 pip install 'my-slides[browser]' 后重试"
            ) from exc
    errors: list[str] = []
    warnings: list[str] = []
    external_requests: list[str] = []
    measurements: dict[str, Any] = {}
    measured_units: list[str] = []
    screenshots: list[dict[str, Any]] = []
    deck_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError("Chromium 尚未安装；请运行 my-slides browser install") from exc
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

        def on_request(request: Any) -> None:
            url = request.url
            if url.startswith(("http://", "https://")):
                external_requests.append(url)

        page.on("request", on_request)
        page.goto(path.resolve().as_uri(), wait_until="load")

        catalog = page.evaluate(
            """() => [...document.querySelectorAll('.slide')].map((slide, index) => ({
              index,
              unitId: slide.getAttribute('data-unit-id') || '',
              role: slide.getAttribute('data-page-role') || '',
              dataSlide: slide.getAttribute('data-slide') || String(index)
            }))"""
        )
        targets: list[int]
        if unit_ids:
            by_unit: dict[str, list[int]] = {}
            for item in catalog:
                if item["unitId"]:
                    by_unit.setdefault(item["unitId"], []).append(item["index"])
            missing = [unit_id for unit_id in unit_ids if unit_id not in by_unit]
            if missing:
                errors.append("HTML 中缺少单元页面：" + "、".join(missing))
                browser.close()
                return {
                    "valid": False,
                    "viewports": {},
                    "external_requests": external_requests,
                    "errors": errors,
                    "warnings": warnings,
                    "measured": True,
                    "measured_units": [],
                    "cached": False,
                }
            targets = [index for unit_id in unit_ids for index in by_unit[unit_id]]
            measured_units = [unit_id for unit_id in unit_ids for _index in by_unit[unit_id]]
        elif slide_indexes is not None:
            targets = list(slide_indexes)
            measured_units = [catalog[i]["unitId"] for i in targets if 0 <= i < len(catalog)]
        else:
            targets = list(range(len(catalog)))
            measured_units = [item["unitId"] for item in catalog if item["unitId"]]

        # 桌面、手机竖屏、手机横屏都按真实窗口测量，不再假设 1920×1080 画布。
        for label, width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("(label) => { window.__mlsViewport = label; }", label)
            # Reset to first slide for deck-level smoke.
            page.evaluate("() => { const pages=[...document.querySelectorAll('.slide')]; pages.forEach((p,i)=>p.classList.toggle('active', i===0)); }")
            page.evaluate(_SETTLE_ANIMATIONS)
            viewport_errors: list[str] = []
            viewport_warnings: list[str] = []
            per_slide: list[dict[str, Any]] = []
            for target in targets:
                page.evaluate(
                    """(index) => {
                      const pages=[...document.querySelectorAll('.slide')];
                      pages.forEach((p,i)=>p.classList.toggle('active', i===index));
                    }""",
                    target,
                )
                page.evaluate(_SETTLE_ANIMATIONS)
                metrics = page.evaluate(
                    """(targetIndex) => {
                      const stage = document.querySelector('[data-deck-stage]');
                      const slides = [...document.querySelectorAll('.slide')];
                      const slide = slides[targetIndex];
                      const rect = stage.getBoundingClientRect();
                      const slideRect = slide.getBoundingClientRect();
                      const active = slides.indexOf(document.querySelector('.slide.active'));
                      const visibleText = [];
                      const outOfBounds = [];
                      const invisibleText = [];
                      const overlaps = [];
                      const textBlocks = 'h1,h2,h3,h4,h5,h6,p,li,td,th,blockquote,figcaption,button';
                      for (const element of slide.querySelectorAll('*')) {
                        if (element.matches('script,style,svg defs,svg title,svg desc')) continue;
                        const style = getComputedStyle(element);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const box = element.getBoundingClientRect();
                        if (box.width < 0.5 || box.height < 0.5) continue;
                        if (box.left < slideRect.left - 2 || box.top < slideRect.top - 2 ||
                            box.right > slideRect.right + 2 || box.bottom > slideRect.bottom + 2) {
                          outOfBounds.push({slide: targetIndex, tag: element.tagName, text: (element.innerText || '').slice(0, 80)});
                        }
                        const text = (element.children.length === 0 ? element.textContent : '')?.trim();
                        if (!text) continue;
                        if (Number(style.opacity) === 0 || style.color === 'rgba(0, 0, 0, 0)' || style.fontSize === '0px') {
                          invisibleText.push({slide: targetIndex, text: text.slice(0, 80)});
                        }
                        visibleText.push({slide: targetIndex, text: text.slice(0, 80), fontSize: parseFloat(style.fontSize)});
                      }
                      const blocks = [...slide.querySelectorAll(textBlocks)].filter(el => {
                        const style = getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && el.innerText.trim();
                      });
                      for (let i = 0; i < blocks.length; i++) for (let j = i + 1; j < blocks.length; j++) {
                        const a = blocks[i], b = blocks[j];
                        if (a.parentElement !== b.parentElement) continue;
                        const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
                        const intersection = Math.max(0, Math.min(ar.right, br.right) - Math.max(ar.left, br.left)) *
                          Math.max(0, Math.min(ar.bottom, br.bottom) - Math.max(ar.top, br.top));
                        const smaller = Math.min(ar.width * ar.height, br.width * br.height);
                        if (smaller > 0 && intersection / smaller > 0.12) overlaps.push({slide: targetIndex, first: a.tagName, second: b.tagName});
                      }
                      const overflow = slide.scrollWidth > slide.clientWidth + 1 || slide.scrollHeight > slide.clientHeight + 1;
                      const chartOverflow = [];
                      const smallText = [];
                      const chartSmallText = [];
                      const chartLabels = [];
                      const inaccessibleCharts = [...slide.querySelectorAll('.mls-chart svg')]
                        .filter(svg => !svg.getAttribute('aria-label') && !svg.querySelector('title,desc')).length;
                      const lowContrast = [];
                      const rgb = value => {
                        const m = value.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                        return m ? [Number(m[1]),Number(m[2]),Number(m[3]),m[4] === undefined ? 1 : Number(m[4])] : null;
                      };
                      const luminance = color => color.slice(0,3).map(v => {
                        const n = v / 255; return n <= .04045 ? n / 12.92 : Math.pow((n + .055) / 1.055, 2.4);
                      }).reduce((sum,v,i) => sum + v * [.2126,.7152,.0722][i], 0);
                      for (const el of slide.querySelectorAll('h1,h2,h3,h4,p,li,td,th,figcaption')) {
                        if (!el.textContent?.trim() || el.getBoundingClientRect().width < 1) continue;
                        const fg = rgb(getComputedStyle(el).color);
                        let parent = el, bg;
                        while (parent && !bg) { const value = rgb(getComputedStyle(parent).backgroundColor); if (value && value[3] === 1) bg = value; parent = parent.parentElement; }
                        if (!fg || fg[3] !== 1) continue;
                        bg ||= [255,255,255,1];
                        const a = luminance(fg), b = luminance(bg), ratio = (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                        const size = parseFloat(getComputedStyle(el).fontSize);
                        if (ratio < (size >= 24 ? 3 : 4.5)) lowContrast.push({text:el.textContent.slice(0,40), ratio:Math.round(ratio*10)/10});
                      }
                      const thresholds = {desktop: {heading: 18, body: 14, note: 11}, 'mobile-portrait': {heading: 12, body: 10, note: 8}, 'mobile-landscape': {heading: 11, body: 9, note: 7}};
                      const threshold = thresholds[window.__mlsViewport] || thresholds.desktop;
                      const isMobileViewport = window.__mlsViewport === 'mobile-portrait' || window.__mlsViewport === 'mobile-landscape';
                      for (const element of slide.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,td,th,blockquote,figcaption,.mls-chart svg text')) {
                        const style = getComputedStyle(element);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const text = element.textContent?.trim();
                        const box = element.getBoundingClientRect();
                        if (!text || box.width < 1 || box.height < 1) continue;
                        const isChart = Boolean(element.closest('.mls-chart'));
                        const role = /^H[1-6]$/.test(element.tagName) ? 'heading' :
                          (element.matches('figcaption,.footnote,.source,.note') || isChart ? 'note' : 'body');
                        let size = parseFloat(style.fontSize);
                        if (isChart) {
                          // SVG font-size is in user coordinates; the screen scale comes from the SVG viewBox.
                          const svg = element.ownerSVGElement;
                          const view = svg?.viewBox?.baseVal;
                          const displayed = svg?.getBoundingClientRect();
                          if (view?.width && view?.height && displayed) size *= Math.min(displayed.width / view.width, displayed.height / view.height);
                          const svgBounds = svg.getBoundingClientRect();
                          if (box.left < svgBounds.left - 2 || box.right > svgBounds.right + 2 ||
                              box.top < svgBounds.top - 2 || box.bottom > svgBounds.bottom + 2) {
                            chartLabels.push({text: text.slice(0, 60), reason: 'outside SVG bounds'});
                          }
                        }
                        if (size < threshold[role] - .25 && !element.closest('[data-qa-small-text="allowed"]')) {
                          // Mobile viewport + chart SVG text is a soft warning (review screenshot),
                          // while desktop chart text below threshold is a hard error like HTML text.
                          if (isChart && isMobileViewport) {
                            chartSmallText.push({text: text.slice(0, 60), role, pixels: Math.round(size * 10) / 10});
                          } else {
                            smallText.push({text: text.slice(0, 60), role, pixels: Math.round(size * 10) / 10});
                          }
                        }
                      }
                      for (const container of slide.querySelectorAll('.chart-container')) {
                        const box = container.getBoundingClientRect();
                        const containerStyle = getComputedStyle(container);
                        const content = {
                          left: box.left + (parseFloat(containerStyle.borderLeftWidth) || 0) + (parseFloat(containerStyle.paddingLeft) || 0),
                          right: box.right - (parseFloat(containerStyle.borderRightWidth) || 0) - (parseFloat(containerStyle.paddingRight) || 0),
                          top: box.top + (parseFloat(containerStyle.borderTopWidth) || 0) + (parseFloat(containerStyle.paddingTop) || 0),
                          bottom: box.bottom - (parseFloat(containerStyle.borderBottomWidth) || 0) - (parseFloat(containerStyle.paddingBottom) || 0),
                        };
                        for (const svg of container.querySelectorAll('svg')) {
                          const svgBox = svg.getBoundingClientRect();
                          if (svgBox.width < 0.5 || svgBox.height < 0.5) continue;
                          if (svgBox.left < content.left - 2 || svgBox.top < content.top - 2 ||
                              svgBox.right > content.right + 2 || svgBox.bottom > content.bottom + 2) {
                            chartOverflow.push({slide: targetIndex, tag: 'svg'});
                          }
                        }
                      }
                      const clipped = [];
                      for (const element of slide.querySelectorAll('*')) {
                        if (element.matches('script,style')) continue;
                        const elementStyle = getComputedStyle(element);
                        if (elementStyle.display === 'none' || elementStyle.visibility === 'hidden') continue;
                        const hides = ['hidden', 'clip', 'scroll', 'auto'].includes(elementStyle.overflowX)
                          || ['hidden', 'clip', 'scroll', 'auto'].includes(elementStyle.overflowY);
                        if (!hides) continue;
                        if (element.scrollWidth > element.clientWidth + 2 || element.scrollHeight > element.clientHeight + 2) {
                          clipped.push({slide: targetIndex, tag: element.tagName, text: (element.innerText || '').slice(0, 80)});
                        }
                      }
                      return {
                        documentWidth: document.documentElement.scrollWidth,
                        stageWidth: rect.width,
                        stageHeight: rect.height,
                        slideCount: slides.length,
                        active,
                        targetIndex,
                        unitId: slide.getAttribute('data-unit-id') || '',
                        overflow,
                        visibleSlides: slides.filter(s => getComputedStyle(s).display !== 'none').length,
                        visibleTextCount: visibleText.length,
                        outOfBounds,
                        invisibleText,
                        overlaps,
                        clipped,
                        chartOverflow, smallText, chartSmallText, chartLabels, inaccessibleCharts, lowContrast
                      };
                    }""",
                    target,
                )
                if evidence_dir is not None and 0 <= target < len(catalog):
                    name = f"{label}-p{target + 1:03d}.png"
                    page.screenshot(path=str(evidence_dir / name), animations="disabled")
                    screenshots.append({"viewport": label, "index": target, "unit_id": metrics["unitId"],
                                        "page": catalog[target].get("dataSlide"), "file": name,
                                        "sha256": hashlib.sha256((evidence_dir / name).read_bytes()).hexdigest()})
                per_slide.append(metrics)
                prefix = f"{label}/slide {target}"
                if metrics["unitId"]:
                    prefix = f"{label}/{metrics['unitId']}"
                if metrics["documentWidth"] > width:
                    viewport_errors.append(f"{prefix}: document overflows horizontally")
                if metrics["stageWidth"] > width + 1 or metrics["stageHeight"] > height + 1:
                    viewport_errors.append(f"{prefix}: deck stage exceeds the viewport")
                if metrics["visibleSlides"] != 1:
                    viewport_errors.append(f"{prefix}: expected one visible slide after activation")
                if metrics["active"] != target:
                    viewport_errors.append(f"{prefix}: failed to activate target slide")
                if metrics["overflow"]:
                    viewport_errors.append(f"{prefix}: slide content is clipped by the viewport")
                if metrics["clipped"]:
                    viewport_errors.append(f"{prefix}: overflow hidden is clipping slide content")
                if metrics["chartOverflow"]:
                    viewport_errors.append(f"{prefix}: chart svg extends outside its chart container")
                if not metrics["visibleTextCount"]:
                    viewport_errors.append(f"{prefix}: no visible slide text was measured")
                if metrics["outOfBounds"]:
                    viewport_errors.append(f"{prefix}: slide elements extend beyond the slide bounds")
                if metrics["invisibleText"]:
                    viewport_errors.append(f"{prefix}: slide contains text hidden by opacity or transparent color")
                if metrics["overlaps"]:
                    viewport_errors.append(f"{prefix}: sibling text blocks overlap")
                if metrics["smallText"]:
                    viewport_errors.append(f"{prefix}: text below readable size: {metrics['smallText'][:3]}")
                if metrics["chartSmallText"]:
                    viewport_warnings.append(
                        f"{prefix}: chart text below readable size (review screenshot): {metrics['chartSmallText'][:3]}"
                    )
                if metrics["chartLabels"]:
                    viewport_errors.append(f"{prefix}: chart label extends beyond SVG: {metrics['chartLabels'][:3]}")
                if metrics["inaccessibleCharts"]:
                    viewport_errors.append(f"{prefix}: chart SVG is missing an accessible summary")
                if metrics["lowContrast"].length:
                    viewport_errors.append(f"{prefix}: text contrast below 4.5:1 (large text 3:1): {metrics['lowContrast'][:3]}")

            # Deck smoke once per viewport (not per unit).
            if len(catalog) > 1 and not unit_ids:
                page.evaluate("() => { const pages=[...document.querySelectorAll('.slide')]; pages.forEach((p,i)=>p.classList.toggle('active', i===0)); }")
                page.keyboard.press("ArrowRight")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                    viewport_errors.append(f"{label}: ArrowRight navigation failed")
                page.keyboard.press("ArrowLeft")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "0":
                    viewport_errors.append(f"{label}: ArrowLeft navigation failed")
                page.locator("#nextSlide").click()
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                    viewport_errors.append(f"{label}: next button navigation failed")
                page.locator("#prevSlide").focus()
                page.keyboard.press("Enter")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "0":
                    viewport_errors.append(f"{label}: keyboard button navigation failed")
                page.evaluate("""() => {
                  const stage = document.querySelector('[data-deck-stage]');
                  const start = new Event('touchstart'); Object.defineProperty(start,'changedTouches',{value:[{clientX:200}]}); stage.dispatchEvent(start);
                  const end = new Event('touchend'); Object.defineProperty(end,'changedTouches',{value:[{clientX:100}]}); stage.dispatchEvent(end);
                }""")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                    viewport_errors.append(f"{label}: touch swipe navigation failed")

            measurements[label] = {"slides": per_slide}
            errors.extend(viewport_errors)
            warnings.extend(viewport_warnings)
        browser.close()
    if evidence_dir is not None:
        prior_manifest = evidence_dir / "measurements.json"
        if prior_manifest.is_file():
            try:
                prior = json.loads(prior_manifest.read_text(encoding="utf-8")).get("evidence", {})
                if prior.get("deck_sha256") == deck_sha and prior.get("rules_version") == QA_RULES_VERSION:
                    selected = set(measured_units)
                    retained = [item for item in prior.get("screenshots", [])
                                if item.get("unit_id") not in selected and (evidence_dir / item.get("file", "")).is_file()]
                    screenshots = retained + screenshots
                    spec_hashes = {**prior.get("spec_sha256", {}), **(spec_hashes or {})}
            except (OSError, ValueError, TypeError):
                pass
        # Contact sheets are generated from the exact captured PNGs, never a second render.
        from PIL import Image, ImageDraw
        for label, _width, _height in VIEWPORTS:
            files = [evidence_dir / item["file"] for item in sorted(screenshots, key=lambda item: item["index"])
                     if item["viewport"] == label]
            if not files:
                continue
            thumb_width, thumb_height = 320, 230
            sheet = Image.new("RGB", (thumb_width * min(3, len(files)), thumb_height * ((len(files) + 2) // 3)), "#eeeeee")
            draw = ImageDraw.Draw(sheet)
            for index, file in enumerate(files):
                with Image.open(file) as source:
                    source.thumbnail((thumb_width - 16, thumb_height - 32))
                    x = index % 3 * thumb_width + (thumb_width - source.width) // 2
                    y = index // 3 * thumb_height + 20
                    sheet.paste(source.convert("RGB"), (x, y))
                    draw.text((index % 3 * thumb_width + 8, index // 3 * thumb_height + 3), file.stem, fill="#111111")
            sheet.save(evidence_dir / f"contact-{label}.png")
    if external_requests:
        errors.append("offline deck requested external resources: " + ", ".join(dict.fromkeys(external_requests)))
    result = {
        "valid": not errors,
        "viewports": measurements,
        "external_requests": external_requests,
        "errors": errors,
        "warnings": warnings,
        "measured": True,
        "measured_units": measured_units,
        "cached": False,
        "input_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if evidence_dir is not None:
        result["evidence"] = {"directory": str(evidence_dir), "screenshots": screenshots,
                              "contacts": [f"contact-{label}.png" for label, _, _ in VIEWPORTS],
                              "deck_sha256": deck_sha, "spec_sha256": spec_hashes or {},
                              "rules_version": QA_RULES_VERSION, "review_status": "unreviewed"}
        (evidence_dir / "measurements.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def record_unit_check_results(
    base: Path,
    unit_ids: list[str],
    *,
    passed: bool,
    deck_path: Path,
) -> None:
    """Persist a check fingerprint bound to the measured deck and built page version.

    不能用当前源文件哈希：源可能已改、正式 index.html 仍是旧构建；否则重建后
    check.current 会在未重测的情况下保持 true。
    """
    from .dependencies import fingerprint_file
    from .state import check_input_fingerprint, read_unit_state, write_unit_state
    from .units import unit_paths

    deck_sha = fingerprint_file(deck_path)
    for unit_id in unit_ids:
        state = read_unit_state(base, unit_id)
        paths = unit_paths(base, unit_id)
        # 绑定最后一次成功构建的页面版本，而不是可能已编辑的 live 源文件。
        html_sha = state["html"].get("build_sha256") or fingerprint_file(paths.page)
        state["check"] = {
            "input_fingerprint": check_input_fingerprint(
                html_sha,
                fingerprint_file(paths.spec),
                deck_sha=deck_sha,
            ),
            "result": "pass" if passed else "fail",
            "current": passed,
            "measured": True,
            "cached": False,
        }
        write_unit_state(base, unit_id, state)


def check_units_on_deck(
    base: Path,
    path: Path,
    unit_ids: list[str],
    *,
    browser: bool = False,
    screenshots: bool = False,
) -> dict[str, Any]:
    """Combine structural deck checks with optional browser measurement for units."""
    from .unit_workflow import split_spec_pages
    from .units import load_units_manifest, unit_paths

    units, _ = load_units_manifest(base, chapters=None)
    expected_page_counts: dict[str, int] = {}
    for unit in units:
        spec_path = unit_paths(base, unit.id).spec
        if not spec_path.is_file():
            continue
        _preamble, pages = split_spec_pages(spec_path.read_text(encoding="utf-8"))
        numbers = [page["number"] for page in pages]
        if pages and numbers == list(range(1, len(pages) + 1)):
            expected_page_counts[unit.id] = len(pages)
    structural = structural_check_deck(
        path,
        expected_units=[unit.id for unit in units],
        expected_page_counts=expected_page_counts,
    )
    errors = list(structural["errors"])
    warnings = list(structural.get("warnings", []))
    browser_result = None
    if browser:
        from .dependencies import fingerprint_file
        deck_sha = fingerprint_file(path) if path.is_file() else None
        evidence_dir = base / ".state" / "visual" / deck_sha[:16] if screenshots and deck_sha else None
        browser_result = check_deck(path, unit_ids=unit_ids, evidence_dir=evidence_dir,
                                    spec_hashes={unit_id: fingerprint_file(unit_paths(base, unit_id).spec) for unit_id in unit_ids})
        errors.extend(browser_result["errors"])
        warnings.extend(browser_result.get("warnings", []))
        record_unit_check_results(
            base,
            unit_ids,
            passed=not browser_result["errors"],
            deck_path=path,
        )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "structural": structural,
        "browser": browser_result,
        "selected_units": unit_ids,
    }
