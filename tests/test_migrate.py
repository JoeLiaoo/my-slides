import argparse
import tempfile
import unittest
from pathlib import Path

from my_slides.cli import init_project, slug, template_chapters
from my_slides.units import (
    detect_format_version,
    migrate_to_units,
    migrate_to_units_preview,
    rollback_units_migration,
    unit_paths,
)


class FormalMigrateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False, format="v1"))

    def tearDown(self):
        self.temp.cleanup()

    def _seed_one_page_chapters(self):
        for index, chapter in enumerate(self.chapters):
            chapter_slug = slug(chapter)
            unit_id = "cover" if index == 0 else f"chapter-{index:02d}-01"
            role = "cover" if index == 0 else "content"
            (self.base / "reports" / f"{chapter_slug}.md").write_text(
                f"# {chapter}\n\nEnough report content for migration mapping.\n",
                encoding="utf-8",
            )
            (self.base / "specs" / f"{chapter_slug}.md").write_text(
                f"## Slide 1 — {chapter}\n页面 ID：{unit_id}\n页面角色：{role}\n"
                "### 目的\nX\n### 核心结论\nY\n### 展示内容\nZ\n"
                "### 证据与来源\nS\n### 限定条件\nL\n### 报告段落映射\nM\n"
                "### 布局意图\nL\n### 图标需求\n无\n",
                encoding="utf-8",
            )
            (self.base / "slides" / "chapters" / f"{chapter_slug}.html").write_text(
                f'<section class="slide" id="{unit_id}" data-page-role="{role}">'
                f"<h1>{chapter}</h1>"
                f'<script type="application/json" class="slide-notes">'
                f'{{"title":"{chapter}","script":"Hi","notes":[]}}</script></section>',
                encoding="utf-8",
            )

    def test_formal_migrate_and_rollback(self):
        self._seed_one_page_chapters()
        preview = migrate_to_units_preview(self.base, self.chapters)
        self.assertTrue(preview["can_migrate"], preview)
        result = migrate_to_units(self.base, self.chapters)
        self.assertTrue(result["migrated"])
        self.assertEqual(detect_format_version(self.base), "v2")
        self.assertTrue((self.base / "units.json").is_file())
        cover = unit_paths(self.base, "cover")
        self.assertTrue(cover.report.is_file())
        self.assertTrue(cover.spec.is_file())
        self.assertTrue(cover.page.is_file())
        self.assertTrue((self.base / "reports" / "report.md").is_file())
        # Approvals should not carry over as chapter approvals.
        self.assertFalse((self.base / ".state" / "approvals.json").is_file())

        rolled = rollback_units_migration(self.base)
        self.assertTrue(rolled["rolled_back"])
        self.assertEqual(detect_format_version(self.base), "v1")
        self.assertFalse((self.base / "units.json").exists())
        self.assertTrue((self.base / "slides" / "chapters").is_dir())


if __name__ == "__main__":
    unittest.main()
