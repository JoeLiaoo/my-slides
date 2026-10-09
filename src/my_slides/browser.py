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


def structural_check_deck(path: Path, *, expected_units: list[str] | None = None) -> dict[str, Any]:
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
    if expected_units is not None:
        if unit_ids != expected_units:
            errors.append(
                "整套单元集合或顺序与 units.json 不一致："
                f"期望 {expected_units}，实际 {unit_ids}"
            )
    covers = sum(1 for slide in slides if slide["role"] == "cover")
    if covers > 1:
        errors.append("整套必须恰好一个 cover 页面")
    if "http://" in text or re.search(r'https://(?!github\.com/)', text):
        # Soft hint — deep offline blocking is done in browser layer.
        pass
    return {"valid": not errors, "errors": errors, "measured": False, "unit_ids": unit_ids}


def check_deck(
    path: Path,
    *,
    unit_ids: list[str] | None = None,
    slide_indexes: list[int] | None = None,
) -> dict[str, Any]:
    """Browser QA. When unit_ids/slide_indexes given, activate each target before measuring."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("浏览器检查需要 Playwright；安装 my-slides[browser] 后运行 my-slides browser install") from exc

    if not path.exists():
        raise ValueError(f"Slides 文件不存在：{path}")
    errors: list[str] = []
    external_requests: list[str] = []
    measurements: dict[str, Any] = {}
    measured_units: list[str] = []
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
            by_unit = {item["unitId"]: item["index"] for item in catalog if item["unitId"]}
            missing = [unit_id for unit_id in unit_ids if unit_id not in by_unit]
            if missing:
                errors.append("HTML 中缺少单元页面：" + "、".join(missing))
                browser.close()
                return {
                    "valid": False,
                    "viewports": {},
                    "external_requests": external_requests,
                    "errors": errors,
                    "measured": True,
                    "measured_units": [],
                    "cached": False,
                }
            targets = [by_unit[unit_id] for unit_id in unit_ids]
            measured_units = list(unit_ids)
        elif slide_indexes is not None:
            targets = list(slide_indexes)
            measured_units = [catalog[i]["unitId"] for i in targets if 0 <= i < len(catalog)]
        else:
            targets = list(range(len(catalog)))
            measured_units = [item["unitId"] for item in catalog if item["unitId"]]

        for label, width, height in (("desktop", 1920, 1080), ("mobile", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            # Reset to first slide for deck-level smoke.
            page.evaluate("() => { const pages=[...document.querySelectorAll('.slide')]; pages.forEach((p,i)=>p.classList.toggle('active', i===0)); }")
            page.wait_for_timeout(50)
            viewport_errors: list[str] = []
            per_slide: list[dict[str, Any]] = []
            for target in targets:
                page.evaluate(
                    """(index) => {
                      const pages=[...document.querySelectorAll('.slide')];
                      pages.forEach((p,i)=>p.classList.toggle('active', i===index));
                    }""",
                    target,
                )
                page.wait_for_timeout(80)
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
                        overlaps
                      };
                    }""",
                    target,
                )
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
                    viewport_errors.append(f"{prefix}: slide content overflows its 16:9 canvas")
                if not metrics["visibleTextCount"]:
                    viewport_errors.append(f"{prefix}: no visible slide text was measured")
                if metrics["outOfBounds"]:
                    viewport_errors.append(f"{prefix}: slide elements extend beyond the slide bounds")
                if metrics["invisibleText"]:
                    viewport_errors.append(f"{prefix}: slide contains text hidden by opacity or transparent color")
                if metrics["overlaps"]:
                    viewport_errors.append(f"{prefix}: sibling text blocks overlap")

            # Deck smoke once per viewport (not per unit).
            if len(catalog) > 1 and not unit_ids:
                page.evaluate("() => { const pages=[...document.querySelectorAll('.slide')]; pages.forEach((p,i)=>p.classList.toggle('active', i===0)); }")
                page.keyboard.press("ArrowRight")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                    viewport_errors.append(f"{label}: ArrowRight navigation failed")
                page.keyboard.press("ArrowLeft")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "0":
                    viewport_errors.append(f"{label}: ArrowLeft navigation failed")

            measurements[label] = {"slides": per_slide}
            errors.extend(viewport_errors)
        browser.close()
    if external_requests:
        errors.append("offline deck requested external resources: " + ", ".join(dict.fromkeys(external_requests)))
    return {
        "valid": not errors,
        "viewports": measurements,
        "external_requests": external_requests,
        "errors": errors,
        "measured": True,
        "measured_units": measured_units,
        "cached": False,
        "input_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


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
) -> dict[str, Any]:
    """Combine structural deck checks with optional browser measurement for units."""
    from .units import load_units_manifest

    units, _ = load_units_manifest(base, chapters=None)
    structural = structural_check_deck(path, expected_units=[unit.id for unit in units])
    errors = list(structural["errors"])
    browser_result = None
    if browser:
        browser_result = check_deck(path, unit_ids=unit_ids)
        errors.extend(browser_result["errors"])
        record_unit_check_results(
            base,
            unit_ids,
            passed=not browser_result["errors"],
            deck_path=path,
        )
    return {
        "valid": not errors,
        "errors": errors,
        "structural": structural,
        "browser": browser_result,
        "selected_units": unit_ids,
    }
