import argparse
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from my_slides.assembly import build_units_deck
from my_slides.commands.init import init_project
from my_slides.state import refresh_unit_currency
from my_slides.theme import THEME_NAME, shell_css, verify_assets
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec, prepare_unit_handoff
from my_slides.units import Unit, unit_paths, write_units_manifest


def _spec(unit_id: str, role: str) -> str:
    return (
        f"## Slide 1 — {unit_id}\n页面 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\nLayout.\n### 图标需求\n无\n"
    )


def _page(unit_id: str, role: str) -> str:
    return (
        f'<section class="slide" data-page-role="{role}" data-unit-id="{unit_id}">'
        f"<h1>{unit_id}</h1>"
        f'<script type="application/json" class="slide-notes">'
        f'{{"title":"{unit_id}","script":"Hi","notes":[]}}</script></section>'
    )


class ThemeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.units = [
            Unit(id="cover", chapter="投资概要", role="cover"),
            Unit(id="summary-01", chapter="投资概要", role="content"),
        ]
        write_units_manifest(self.base, self.units)
        for unit in self.units:
            paths = unit_paths(self.base, unit.id)
            paths.report.write_text(f"# {unit.id}\n\n" + "Enough report text for approval. " * 3, encoding="utf-8")
            paths.spec.write_text(_spec(unit.id, unit.role), encoding="utf-8")
            paths.page.write_text(_page(unit.id, unit.role), encoding="utf-8")
            approve_unit_report(self.base, unit, when="t0", project_root=self.root)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root)
        self.cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}

    def tearDown(self):
        self.temp.cleanup()

    def test_packaged_assets_match_manifest(self):
        self.assertEqual(verify_assets(), [])
        css = shell_css("#A6192E")
        self.assertIn("100dvh", css)
        self.assertIn("--brand: #A6192E", css)
        self.assertNotIn("fonts.googleapis", css)
        self.assertNotIn("@import", css)
        self.assertIn("PingFang SC", css)

    def test_preview_and_deck_share_shell(self):
        output, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        deck = output.read_text(encoding="utf-8")
        preview = unit_paths(self.base, "cover").preview.read_text(encoding="utf-8")
        page = unit_paths(self.base, "cover").page.read_text(encoding="utf-8")
        shared = shell_css(self.cfg["brand_color"])
        self.assertIn(shared, deck)
        self.assertIn(shared, preview)
        self.assertIn(f'my-slides-theme" content="{THEME_NAME}"', preview)
        self.assertIn('class="slide active"', preview)
        self.assertEqual(deck.count('id="controls"'), 1)
        self.assertNotIn("fitSlides", deck)
        self.assertNotIn("1920px", deck)
        self.assertNotIn("function goTo", page)
        self.assertNotIn('id="controls"', page)
        self.assertNotIn("fonts.googleapis", preview)
        self.assertNotIn("fonts.googleapis", deck)

    def test_theme_change_expires_html_not_approvals_and_rebuilds_match(self):
        from my_slides.browser import record_unit_check_results
        from my_slides.theme import theme_cache_fields

        deck, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        record_unit_check_results(self.base, [unit.id for unit in self.units], passed=True, deck_path=deck)
        self.assertTrue(refresh_unit_currency(self.base, self.units[1], project_root=self.root)["check"]["current"])

        def bumped_fields():
            data = dict(theme_cache_fields())
            data["shell_version"] = "bumped"
            return data

        with (
            patch("my_slides.assembly.theme_cache_fields", bumped_fields),
            patch("my_slides.assembly.shell_fingerprint", lambda: "bumped-shell"),
            patch("my_slides.theme.shell_fingerprint", lambda: "bumped-shell"),
        ):
            state = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
            self.assertTrue(state["report"]["current"])
            self.assertTrue(state["spec"]["current"])
            self.assertFalse(state["html"]["current"], state["reasons"])
            self.assertFalse(state["check"]["current"])
            incremental, errors, plan = build_units_deck(self.base, self.cfg, unit_ids=["cover"], write=True)
            self.assertEqual(errors, [])
            self.assertNotIn("summary-01", plan["reused"])
            full, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
            self.assertEqual(errors, [])
            self.assertEqual(incremental.read_text(encoding="utf-8"), full.read_text(encoding="utf-8"))

    def test_prepare_slides_handoff_lists_static_components(self):
        output = prepare_unit_handoff(self.base, self.root, self.units, "slides", stamp="t")
        text = output.read_text(encoding="utf-8")
        self.assertIn("stat-card", text)
        self.assertIn("vs-container", text)
        self.assertIn("table-wrap", text)
        self.assertIn("chart-container", text)
        self.assertIn("slides/previews/", text)
        self.assertNotIn("onclick", text)

    def test_wheel_contains_theme_assets(self):
        uv = shutil.which("uv")
        if not uv:
            self.skipTest("需要 uv 才能打 wheel")
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [uv, "build", "--wheel", "-o", tmp],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            wheels = list(Path(tmp).glob("*.whl"))
            self.assertEqual(len(wheels), 1, wheels)
            with zipfile.ZipFile(wheels[0]) as archive:
                names = archive.namelist()
        for suffix in (
            "slides_theme/upstream/viewport-base.css",
            "slides_theme/upstream/components.css",
            "slides_theme/upstream/editorial-light.css",
            "slides_theme/upstream/LICENSE",
            "slides_theme/adapt.css",
            "slides_theme/manifest.json",
            "slides_theme/component-examples.md",
        ):
            self.assertTrue(any(name.endswith(suffix) for name in names), suffix)


def _slide(inner: str) -> str:
    from my_slides.theme import render_document

    section = (
        '<section class="slide" data-page-role="content" data-unit-id="layout">'
        f"{inner}"
        '<script type="application/json" class="slide-notes">'
        '{"title":"布局","script":"说明这一页","notes":[]}</script></section>'
    )
    return render_document([section], [], title="布局", brand_color="#A6192E", has_assets=False, kind="preview")


def _measure(html: str, width: int, height: int, script: str, *, media: str = "screen") -> dict:
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "slide.html"
        path.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            external: list[str] = []
            page.on("request", lambda request: external.append(request.url) if request.url.startswith(("http://", "https://")) else None)
            page.emulate_media(media=media)
            page.set_viewport_size({"width": width, "height": height})
            page.goto(path.resolve().as_uri(), wait_until="load")
            page.evaluate(
                """async () => {
                  const pending = document.getAnimations().filter((animation) => {
                    const timing = animation.effect && animation.effect.getTiming();
                    return timing && timing.iterations !== Infinity;
                  });
                  await Promise.race([
                    Promise.all(pending.map((animation) => animation.finished.catch(() => undefined))),
                    new Promise((resolve) => setTimeout(resolve, 2000))
                  ]);
                }"""
            )
            result = page.evaluate(script)
            browser.close()
    result["external"] = external
    return result


class ComponentLayoutBrowserTests(unittest.TestCase):
    def setUp(self):
        from my_slides.browser_runtime import browser_status

        if not browser_status()["chromium_installed"]:
            self.skipTest("optional Playwright Chromium browser is not installed")

    def test_three_stat_cards_stay_inside_mobile_portrait(self):
        cards = "".join(
            f'<div class="stat-card"><p class="stat-number blue">{value}</p>'
            f"<p class=\"stat-label\">{label}</p><p class=\"stat-desc\">口径</p></div>"
            for value, label in (("12%", "收入增速"), ("8%", "毛利率"), ("3%", "净利率"))
        )
        html = _slide(f"<h2>关键指标</h2><div class=\"stats-row\">{cards}</div>")
        measured = _measure(
            html,
            390,
            844,
            """() => {
              const slide = document.querySelector('.slide.active').getBoundingClientRect();
              const cards = [...document.querySelectorAll('.stat-card')].map((card) => {
                const box = card.getBoundingClientRect();
                return {left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height};
              });
              return {slide: {left: slide.left, right: slide.right, top: slide.top, bottom: slide.bottom}, cards};
            }""",
        )
        self.assertEqual(measured["external"], [])
        self.assertEqual(len(measured["cards"]), 3)
        slide = measured["slide"]
        previous_bottom = slide["top"]
        for card in measured["cards"]:
            self.assertGreater(card["width"], 40, card)
            self.assertGreaterEqual(card["left"], slide["left"] - 2, card)
            self.assertLessEqual(card["right"], slide["right"] + 2, card)
            self.assertGreaterEqual(card["top"], slide["top"] - 2, card)
            self.assertLessEqual(card["bottom"], slide["bottom"] + 2, card)
            self.assertGreaterEqual(card["top"], previous_bottom - 2, card)
            previous_bottom = card["bottom"]

    def test_chart_svg_stays_inside_container_on_screen_and_print(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="560">'
            '<rect width="1100" height="560" fill="#d0d4dc"/></svg>'
        )
        html = _slide(f'<h2>趋势</h2><div class="chart-container"><div class="mls-chart">{svg}</div></div>')
        script = """() => {
          const container = document.querySelector('.chart-container');
          const box = container.getBoundingClientRect();
          const style = getComputedStyle(container);
          const content = {
            left: box.left + (parseFloat(style.borderLeftWidth) || 0) + (parseFloat(style.paddingLeft) || 0),
            right: box.right - (parseFloat(style.borderRightWidth) || 0) - (parseFloat(style.paddingRight) || 0),
            top: box.top + (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.paddingTop) || 0),
            bottom: box.bottom - (parseFloat(style.borderBottomWidth) || 0) - (parseFloat(style.paddingBottom) || 0),
          };
          const svgBox = container.querySelector('svg').getBoundingClientRect();
          const slide = document.querySelector('.slide.active').getBoundingClientRect();
          return {
            content, slide: {left: slide.left, right: slide.right, top: slide.top, bottom: slide.bottom},
            svg: {left: svgBox.left, right: svgBox.right, top: svgBox.top, bottom: svgBox.bottom, width: svgBox.width, height: svgBox.height}
          };
        }"""
        for media in ("screen", "print"):
            measured = _measure(html, 1920, 1080, script, media=media)
            self.assertEqual(measured["external"], [], media)
            svg_box = measured["svg"]
            content = measured["content"]
            slide = measured["slide"]
            self.assertGreater(svg_box["width"], 40, measured)
            self.assertGreater(svg_box["height"], 40, measured)
            self.assertGreaterEqual(svg_box["left"], content["left"] - 2, measured)
            self.assertLessEqual(svg_box["right"], content["right"] + 2, measured)
            self.assertGreaterEqual(svg_box["top"], content["top"] - 2, measured)
            self.assertLessEqual(svg_box["bottom"], content["bottom"] + 2, measured)
            self.assertGreaterEqual(svg_box["left"], slide["left"] - 2, measured)
            self.assertLessEqual(svg_box["right"], slide["right"] + 2, measured)
            self.assertGreaterEqual(svg_box["top"], slide["top"] - 2, measured)
            self.assertLessEqual(svg_box["bottom"], slide["bottom"] + 2, measured)
            ratio = svg_box["width"] / svg_box["height"]
            self.assertAlmostEqual(ratio, 1100 / 560, delta=0.08, msg=measured)


if __name__ == "__main__":
    unittest.main()
