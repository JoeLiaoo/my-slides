import tempfile
import unittest
from pathlib import Path

from my_slides.browser import structural_check_deck


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


if __name__ == "__main__":
    unittest.main()
