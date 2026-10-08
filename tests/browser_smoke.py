"""Exercise a generated offline presentation in desktop and mobile Chromium."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def inspect_page(page, width: int, height: int) -> dict:
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    return page.evaluate("""() => {
      const stage = document.querySelector('[data-deck-stage]');
      const slides = [...document.querySelectorAll('.slide')];
      const rect = stage.getBoundingClientRect();
      const active = document.querySelector('.slide.active');
      return {
        viewport: [innerWidth, innerHeight],
        documentWidth: document.documentElement.scrollWidth,
        stage: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        slideCount: slides.length,
        activeIndex: slides.indexOf(active),
        activeText: active?.innerText || '',
        overflowingSlides: slides.filter(s => s.scrollWidth > s.clientWidth + 1 || s.scrollHeight > s.clientHeight + 1).length,
      };
    }""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--screenshots", type=Path, default=Path("output/playwright"))
    args = parser.parse_args()
    html_path = args.html.resolve()
    if not html_path.exists():
        raise SystemExit(f"HTML file does not exist: {html_path}")
    args.screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    external_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: external_requests.append(request.url) if request.url.startswith(("http://", "https://")) else None)
        page.goto(html_path.as_uri(), wait_until="load")
        results = {}
        for name, width, height in (("desktop", 1920, 1080), ("mobile", 390, 844)):
            results[name] = inspect_page(page, width, height)
            page.screenshot(path=str(args.screenshots / f"{name}.png"), full_page=True)
            page.keyboard.press("ArrowRight")
            if results[name]["slideCount"] > 1 and page.locator(".slide.active").count() != 1:
                errors.append(f"{name}: navigation did not leave exactly one active slide")
            page.keyboard.press("ArrowLeft")
            if results[name]["documentWidth"] > width:
                errors.append(f"{name}: horizontal overflow ({results[name]['documentWidth']} > {width})")
            if results[name]["stage"]["width"] > width + 1:
                errors.append(f"{name}: deck stage wider than viewport")
            if results[name]["overflowingSlides"]:
                errors.append(f"{name}: {results[name]['overflowingSlides']} slides contain overflowing content")
        browser.close()
    report = {"html": str(html_path), "viewports": results, "external_requests": external_requests, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
