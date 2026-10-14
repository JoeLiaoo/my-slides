from __future__ import annotations

import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.commands.prepare import prepare
from my_slides.commands.validate import run as validate


VALID_ROW = "| N-001 | AI revenue | 22; 150; 650 | 亿美元 | Q1 2024–Q1 2026 | Research Org《AI Revenue Report》（2026-01） | https://example.org/report | 头部 AI 原生公司公开 ARR 合计；市场估算 |\n"


class EvidenceResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_creates_number_list_and_validation_rejects_empty_list(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare(argparse.Namespace(kind="evidence-research", project=str(self.root), json=True)), 0)
        handoff = self.base / "work" / "evidence-research.md"
        numbers = self.base / "research" / "numbers.md"
        self.assertTrue(handoff.is_file())
        self.assertTrue(numbers.is_file())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(validate(argparse.Namespace(kind="evidence-research", project=str(self.root), json=True)), 1)
        self.assertIn("至少需要一条数字记录", out.getvalue())

    def test_number_list_requires_normalized_citation_and_public_url(self):
        numbers = self.base / "research" / "numbers.md"
        numbers.parent.mkdir(parents=True, exist_ok=True)
        numbers.write_text("# Numbers\n\n" + VALID_ROW, encoding="utf-8")
        self.assertEqual(validate(argparse.Namespace(kind="evidence-research", project=str(self.root), json=True)), 0)
        numbers.write_text(
            "# Numbers\n\n| N-001 | AI revenue | 150 | 亿美元 | 2025 | Unclear source | no-url | 口径未注明 |\n",
            encoding="utf-8",
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(validate(argparse.Namespace(kind="evidence-research", project=str(self.root), json=True)), 1)
        self.assertIn("来源须符合", out.getvalue())
        self.assertIn("公开出处 URL", out.getvalue())


if __name__ == "__main__":
    unittest.main()
