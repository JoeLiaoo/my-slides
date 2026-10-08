"""Headless Chromium validation for the generated standalone deck."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def check_deck(path: Path) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("浏览器检查需要 Playwright；安装 my-slides[browser] 后运行 my-slides browser install") from exc

    if not path.exists():
        raise ValueError(f"Slides 文件不存在：{path}")
    errors: list[str] = []
    external_requests: list[str] = []
    measurements: dict[str, Any] = {}
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError("Chromium 尚未安装；请运行 my-slides browser install") from exc
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: external_requests.append(request.url) if request.url.startswith(("http://", "https://")) else None)
        page.goto(path.resolve().as_uri(), wait_until="load")
        for label, width, height in (("desktop", 1920, 1080), ("mobile", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => {
              const stage = document.querySelector('[data-deck-stage]');
              const slides = [...document.querySelectorAll('.slide')];
              const rect = stage.getBoundingClientRect();
              const active = slides.indexOf(document.querySelector('.slide.active'));
              const visibleText = [];
              const outOfBounds = [];
              const invisibleText = [];
              const overlaps = [];
              const textBlocks = 'h1,h2,h3,h4,h5,h6,p,li,td,th,blockquote,figcaption,button';
              for (const [slideIndex, slide] of slides.entries()) {
                const slideRect = slide.getBoundingClientRect();
                for (const element of slide.querySelectorAll('*')) {
                  if (element.matches('script,style,svg defs,svg title,svg desc')) continue;
                  const style = getComputedStyle(element);
                  if (style.display === 'none' || style.visibility === 'hidden') continue;
                  const box = element.getBoundingClientRect();
                  if (box.width < 0.5 || box.height < 0.5) continue;
                  if (box.left < slideRect.left - 2 || box.top < slideRect.top - 2 ||
                      box.right > slideRect.right + 2 || box.bottom > slideRect.bottom + 2) {
                    outOfBounds.push({slide: slideIndex, tag: element.tagName, text: (element.innerText || '').slice(0, 80)});
                  }
                  const text = (element.children.length === 0 ? element.textContent : '')?.trim();
                  if (!text) continue;
                  if (Number(style.opacity) === 0 || style.color === 'rgba(0, 0, 0, 0)' || style.fontSize === '0px') {
                    invisibleText.push({slide: slideIndex, text: text.slice(0, 80)});
                  }
                  visibleText.push({slide: slideIndex, text: text.slice(0, 80), fontSize: parseFloat(style.fontSize)});
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
                  if (smaller > 0 && intersection / smaller > 0.12) overlaps.push({slide: slideIndex, first: a.tagName, second: b.tagName});
                }
              }
              return {
                documentWidth: document.documentElement.scrollWidth,
                stageWidth: rect.width,
                stageHeight: rect.height,
                slideCount: slides.length,
                active,
                overflow: slides.map(s => s.scrollWidth > s.clientWidth + 1 || s.scrollHeight > s.clientHeight + 1),
                visibleSlides: slides.filter(s => getComputedStyle(s).display !== 'none').length,
                visibleTextCount: visibleText.length,
                outOfBounds,
                invisibleText,
                overlaps
              };
            }""")
            measurements[label] = metrics
            if metrics["documentWidth"] > width:
                errors.append(f"{label}: document overflows horizontally")
            if metrics["stageWidth"] > width + 1 or metrics["stageHeight"] > height + 1:
                errors.append(f"{label}: deck stage exceeds the viewport")
            if metrics["slideCount"] == 0 or metrics["visibleSlides"] != 1:
                errors.append(f"{label}: expected one visible slide")
            if any(metrics["overflow"]):
                errors.append(f"{label}: slide content overflows its 16:9 canvas")
            if metrics["active"] != 0:
                errors.append(f"{label}: initial slide is not the first slide")
            if not metrics["visibleTextCount"]:
                errors.append(f"{label}: no visible slide text was measured")
            if metrics["outOfBounds"]:
                errors.append(f"{label}: slide elements extend beyond the slide bounds")
            if metrics["invisibleText"]:
                errors.append(f"{label}: slide contains text hidden by opacity or transparent color")
            if metrics["overlaps"]:
                errors.append(f"{label}: sibling text blocks overlap")
            if metrics["slideCount"] > 1:
                page.keyboard.press("ArrowRight")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                    errors.append(f"{label}: ArrowRight navigation failed")
                page.keyboard.press("ArrowLeft")
                if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "0":
                    errors.append(f"{label}: ArrowLeft navigation failed")
                if label == "mobile":
                    page.evaluate("""() => {
                      const target = document.querySelector('[data-deck-stage]');
                      const start = new Touch({identifier: 1, target, clientX: 300, clientY: 200});
                      const end = new Touch({identifier: 1, target, clientX: 200, clientY: 200});
                      target.dispatchEvent(new TouchEvent('touchstart', {bubbles: true, changedTouches: [start], touches: [start]}));
                      target.dispatchEvent(new TouchEvent('touchend', {bubbles: true, changedTouches: [end], touches: []}));
                    }""")
                    if page.evaluate("document.querySelector('.slide.active')?.dataset.slide") != "1":
                        errors.append("mobile: touch swipe navigation failed")
        browser.close()
    if external_requests:
        errors.append("offline deck requested external resources: " + ", ".join(external_requests))
    return {"valid": not errors, "viewports": measurements, "external_requests": external_requests, "errors": errors}
