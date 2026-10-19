"""Inline SVG diagrams must remain independent after deck assembly."""

import unittest

from my_slides.assembly import namespace_inline_svg_ids
from my_slides.slide_fragments import SlideFragmentParser


class DiagramSvgTests(unittest.TestCase):
    def test_multiple_diagrams_reuse_local_ids_safely(self):
        diagram = (
            '<svg viewBox="0 0 100 50" aria-labelledby="title desc">'
            '<title id="title">机制</title><desc id="desc">从输入到输出</desc>'
            '<defs><marker id="arrow"><path d="M0 0L3 3"/></marker></defs>'
            '<path marker-end="url(#arrow)" d="M0 0L3 3"/>'
            '<use href="#arrow"/></svg>'
        )
        combined = namespace_inline_svg_ids(diagram * 2, "industry-chain", 1)
        for index in range(2):
            prefix = f"mls-industry-chain-p1-svg{index}-"
            self.assertIn(f'id="{prefix}title"', combined)
            self.assertIn(f'aria-labelledby="{prefix}title {prefix}desc"', combined)
            self.assertIn(f'marker-end="url(#{prefix}arrow)"', combined)
            self.assertIn(f'href="#{prefix}arrow"', combined)
        self.assertNotIn('id="arrow"', combined)

    def test_duplicate_ids_in_one_diagram_fail(self):
        with self.assertRaisesRegex(ValueError, "重复 id"):
            namespace_inline_svg_ids('<svg><title id="same">A</title><desc id="same">B</desc></svg>', "u", 2)

    def test_text_outside_diagram_unchanged(self):
        source = '<p id="intro">文字</p><svg><title id="intro">图解</title></svg>'
        result = namespace_inline_svg_ids(source, "u", 1)
        self.assertIn('<p id="intro">文字</p>', result)
        self.assertIn('<title id="mls-u-p1-svg0-intro">', result)

    def test_arrow_marker_survives_fragment_validation(self):
        fragment = ('<section class="slide" data-unit-id="u" data-page-role="content">'
                    '<svg viewBox="0 0 100 100" role="img" aria-labelledby="label">'
                    '<title id="label">流向</title><defs><marker id="arrow" markerWidth="8" '
                    'markerHeight="8" refX="4" refY="4" orient="auto">'
                    '<path d="M0 0L8 4L0 8"/></marker></defs>'
                    '<path d="M1 1L90 90" marker-end="url(#arrow)"/></svg>'
                    '<script type="application/json" class="slide-notes">{}</script></section>')
        parser = SlideFragmentParser()
        parser.feed(fragment)
        self.assertFalse(parser.errors, parser.errors)
        self.assertIn('marker-end="url(#arrow)"', str(parser.slides))

    def test_marker_cannot_load_external_resource(self):
        parser = SlideFragmentParser()
        parser.feed('<section class="slide"><svg><path marker-end="url(https://example.org/arrow.svg)"/></svg></section>')
        self.assertTrue(any("本地 marker" in error for error in parser.errors), parser.errors)


if __name__ == "__main__":
    unittest.main()
