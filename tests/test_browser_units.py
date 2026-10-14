import tempfile
import unittest
from pathlib import Path

from my_slides.browser import _deck_slides, structural_check_deck, check_deck
from my_slides.browser_runtime import browser_status
from my_slides.theme import render_document


class BrowserUnitChecks(unittest.TestCase):
    @unittest.skipUnless(browser_status()["chromium_installed"], "Playwright Chromium unavailable")
    def test_multislide_screenshots_and_contact_sheets_are_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            deck = directory / "index.html"
            pages = [f'<section class="slide" data-unit-id="sample" data-page-role="content" data-slide="{i}"><h1>Page {i + 1}</h1></section>'
                     for i in range(2)]
            pages.append('<section class="slide" data-unit-id="other" data-page-role="content" data-slide="2"><h1>Other page</h1></section>')
            deck.write_text(render_document(pages, [], title="Capture", brand_color="#A6192E", has_assets=False), encoding="utf-8")
            result = check_deck(deck, unit_ids=["sample"], evidence_dir=directory / "evidence", spec_hashes={"sample": "spec-v1"})
            self.assertTrue(result["valid"], result["errors"])
            evidence = result["evidence"]
            self.assertEqual(len(evidence["screenshots"]), 6)
            self.assertEqual(len(evidence["contacts"]), 3)
            self.assertTrue(all((directory / "evidence" / item["file"]).stat().st_size > 100 for item in evidence["screenshots"]))
            self.assertTrue(all((directory / "evidence" / name).is_file() for name in evidence["contacts"]))
            self.assertEqual(evidence["spec_sha256"]["sample"], "spec-v1")
            second = check_deck(deck, unit_ids=["other"], evidence_dir=directory / "evidence", spec_hashes={"other": "spec-v2"})
            self.assertTrue(second["valid"], second["errors"])
            self.assertEqual(len(second["evidence"]["screenshots"]), 9)
            self.assertEqual(second["evidence"]["spec_sha256"], {"sample": "spec-v1", "other": "spec-v2"})

    def test_structural_check_detects_generator_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(
                '<meta name="generator" content="my-slides">'
                '<section class="slide" data-unit-id="cover" data-page-role="cover"></section>'
                '<section class="slide" data-unit-id="summary-01" data-page-role="content"></section>',
                encoding="utf-8",
            )
            ok = structural_check_deck(path, expected_units=["cover", "summary-01"])
            self.assertTrue(ok["valid"], ok["errors"])
            bad = structural_check_deck(path, expected_units=["summary-01", "cover"])
            self.assertFalse(bad["valid"])
            self.assertTrue(any("顺序" in error for error in bad["errors"]))

    def test_structural_check_ignores_unit_ids_inside_css(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(
                '<meta name="generator" content="my-slides">'
                '<style>@scope ([data-unit-id="cover"]) { h1 { color: #333 } }</style>'
                '<section class="slide" data-unit-id="cover" data-page-role="cover"></section>',
                encoding="utf-8",
            )
            result = structural_check_deck(path, expected_units=["cover"])
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["unit_ids"], ["cover"])

    def test_slide_count_uses_class_token_not_trailing_space(self):
        pages = ['<section class="slide active" data-page-role="cover"><h1>Cover</h1></section>']
        pages.extend(
            f'<section class="slide" data-page-role="content"><h1>Page {index}</h1></section>'
            for index in range(1, 6)
        )
        text = (
            '<style>.slide { color: red } /* class="slide " */</style>'
            '<p>正文里出现 class="slide " 和 slide 都不算一页。</p>'
            + "".join(pages)
        )
        self.assertEqual(len(_deck_slides(text)), 6)
        self.assertNotEqual(text.count('class="slide '), 6)

    @unittest.skipUnless(browser_status()["chromium_installed"], "Playwright Chromium unavailable")
    def test_chart_svg_text_is_warning_in_mobile_and_error_on_desktop(self):
        """A fixed-size SVG chart label passes desktop, becomes a warning on phone viewports."""
        from my_slides.theme import render_document

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            deck = directory / "chart.html"
            chart_svg = (
                '<svg viewBox="0 0 1100 560" width="1100" height="560" role="img" aria-label="Revenue chart">'
                '<title>Revenue chart</title>'
                '<text x="20" y="40" font-size="14">2024</text>'
                '<text x="20" y="540" font-size="14">baseline</text>'
                '</svg>'
            )
            slide = (
                '<section class="slide" data-unit-id="summary" data-page-role="content" data-slide="0">'
                '<h1>Revenue</h1>'
                f'<div class="mls-chart">{chart_svg}</div>'
                '</section>'
            )
            deck.write_text(render_document([slide], [], title="Chart QA", brand_color="#A6192E", has_assets=True), encoding="utf-8")
            result = check_deck(deck, unit_ids=["summary"])

            # Desktop chart text at the 1100px native size clears the 11px note threshold.
            desktop_slides = result["viewports"]["desktop"]["slides"]
            self.assertFalse(any(item.get("smallText") for item in desktop_slides), desktop_slides)
            self.assertTrue(result["valid"], result["errors"])

            # On phone viewports the same SVG renders tiny, so the gate records chartSmallText
            # and surfaces it as a warning, never as an error.
            for label in ("mobile-portrait", "mobile-landscape"):
                slides = result["viewports"][label]["slides"]
                self.assertTrue(
                    any(item.get("chartSmallText") for item in slides),
                    (label, slides),
                )
                self.assertFalse(
                    any(item.get("smallText") for item in slides),
                    (label, slides),
                )
            chart_warnings = [warning for warning in result["warnings"] if "chart text below readable size" in warning]
            self.assertTrue(chart_warnings, result["warnings"])
            self.assertNotIn(
                "text below readable size",
                "\n".join(result["errors"]),
            )

    def test_check_deck_raises_when_pillow_missing_for_screenshots(self, monkeypatch=None):
        """Missing Pillow on the screenshots path returns a clear install hint, not ImportError."""
        import sys as _sys
        import types as _types

        real_pil = _sys.modules.pop("PIL", None)
        real_image = _sys.modules.pop("PIL.Image", None)
        real_draw = _sys.modules.pop("PIL.ImageDraw", None)

        class _StubPIL(_types.ModuleType):
            def __getattr__(self, name):
                raise ImportError("No module named 'PIL'")

        stub = _StubPIL("PIL")
        _sys.modules["PIL"] = stub
        try:
            from my_slides.browser import check_deck

            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                deck = directory / "index.html"
                deck.write_text(render_document(
                    ['<section class="slide" data-unit-id="x" data-page-role="content" data-slide="0"><h1>x</h1></section>'],
                    [], title="X", brand_color="#A6192E", has_assets=False,
                ), encoding="utf-8")
                evidence = directory / "evidence"
                with self.assertRaises(RuntimeError) as context:
                    check_deck(deck, unit_ids=["x"], evidence_dir=evidence)
                self.assertIn("Pillow", str(context.exception))
                self.assertIn("my-slides[browser]", str(context.exception))
        finally:
            _sys.modules.pop("PIL", None)
            if real_pil is not None:
                _sys.modules["PIL"] = real_pil
            if real_image is not None:
                _sys.modules["PIL.Image"] = real_image
            if real_draw is not None:
                _sys.modules["PIL.ImageDraw"] = real_draw


if __name__ == "__main__":
    unittest.main()
