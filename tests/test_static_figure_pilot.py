import unittest
from pathlib import Path

from my_slides.examples_index import select_examples
from my_slides.slide_fragments import SlideFragmentParser


ROOT = Path(__file__).resolve().parents[1] / "skills" / "my-slides-workflow" / "examples" / "technology" / "02-batching-static"


class StaticFigurePilotTests(unittest.TestCase):
    def test_example_and_control_are_safe_single_page_fragments(self):
        for name in ("page.html", "text-only.html"):
            with self.subTest(name=name):
                parser = SlideFragmentParser()
                parser.feed((ROOT / name).read_text(encoding="utf-8"))
                parser.close()
                self.assertEqual(parser.errors, [])
                self.assertEqual(len(parser.slides), 1)
                self.assertTrue(parser.slides[0]["has_notes"])

    def test_mechanism_query_finds_static_example(self):
        matches = select_examples("推理请求排队与批处理的技术过程", limit=2)
        self.assertIn("examples/technology/02-batching-static", [match.path for match in matches])


if __name__ == "__main__":
    unittest.main()
