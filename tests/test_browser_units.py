import tempfile
import unittest
from pathlib import Path

from my_slides.browser import _deck_slides, structural_check_deck


class BrowserUnitChecks(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
