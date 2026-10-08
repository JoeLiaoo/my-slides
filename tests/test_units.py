import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.cli import init_project, slug, template_chapters
from my_slides.units import (
    UnitsError,
    assemble_report,
    detect_format_version,
    dump_units_manifest,
    list_units_status,
    load_units_manifest,
    migrate_to_units_preview,
    unit_paths,
    validate_units,
    write_units_manifest,
    Unit,
)


class UnitsFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()

    def tearDown(self):
        self.temp.cleanup()

    def init_v1(self):
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def write_v2(self, units: list[Unit], *, reports: dict[str, str] | None = None):
        self.init_v1()
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            paths.report.parent.mkdir(parents=True, exist_ok=True)
            paths.spec.parent.mkdir(parents=True, exist_ok=True)
            paths.page.parent.mkdir(parents=True, exist_ok=True)
            body = (reports or {}).get(unit.id, f"# {unit.id}\n\nUnit body for {unit.chapter}.\n")
            paths.report.write_text(body, encoding="utf-8")
            paths.spec.write_text(f"## Slide 1 — {unit.id}\n页面 ID：{unit.id}\n页面角色：{unit.role}\n", encoding="utf-8")
            paths.page.write_text(f'<section class="slide" id="{unit.id}" data-page-role="{unit.role}"></section>', encoding="utf-8")

    def test_detect_format_version_defaults_to_v1(self):
        self.init_v1()
        self.assertEqual(detect_format_version(self.base), "v1")
        self.assertFalse((self.base / "units.json").exists())

    def test_units_manifest_rejects_duplicate_and_bad_cover(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="content"),
            Unit(id="cover", chapter=self.chapters[1], role="cover"),
        ]
        errors = validate_units(units, self.chapters)
        self.assertTrue(any("重复" in error for error in errors))
        self.assertTrue(any("cover" in error for error in errors))

    def test_units_manifest_round_trip_and_paths(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="industry-demand-01", chapter=self.chapters[2], role="content"),
        ]
        self.init_v1()
        write_units_manifest(self.base, units)
        loaded, errors = load_units_manifest(self.base, self.chapters)
        self.assertEqual(errors, [])
        self.assertEqual([unit.id for unit in loaded], ["cover", "industry-demand-01"])
        self.assertEqual(detect_format_version(self.base), "v2")
        paths = unit_paths(self.base, "industry-demand-01")
        self.assertEqual(paths.report, self.base / "reports" / "units" / "industry-demand-01.md")
        self.assertEqual(paths.spec, self.base / "specs" / "units" / "industry-demand-01.md")
        self.assertEqual(paths.page, self.base / "slides" / "pages" / "industry-demand-01.html")

    def test_assemble_report_rewrites_relative_links(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        wiki = "See [company](../../wiki/company.md) and [source](../../../memo.md)."
        self.write_v2(
            units,
            reports={
                "cover": "# Cover\n\nOpening.\n",
                "summary-01": f"# Summary\n\n{wiki}\n",
            },
        )
        (self.base / "wiki" / "company.md").write_text("# Company\n", encoding="utf-8")
        (self.root / "memo.md").write_text("memo", encoding="utf-8")
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [])
        assembled = (self.base / "reports" / "report.md").read_text(encoding="utf-8")
        self.assertEqual(document, assembled)
        self.assertIn("[company](../wiki/company.md)", assembled)
        self.assertIn("[source](../../memo.md)", assembled)
        self.assertNotIn("../../wiki/company.md", assembled)

    def test_units_list_reports_missing_artifacts(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        self.write_v2(units)
        unit_paths(self.base, "summary-01").page.unlink()
        status = list_units_status(self.base, self.chapters)
        self.assertEqual(status["format_version"], "v2")
        self.assertEqual(len(status["missing"]), 1)
        self.assertEqual(status["missing"][0]["id"], "summary-01")
        self.assertEqual(status["missing"][0]["artifact"], "page")

    def test_migrate_dry_run_is_read_only_and_surfaces_page_ids(self):
        self.init_v1()
        chapter = self.chapters[0]
        chapter_slug = slug(chapter)
        (self.base / "reports" / f"{chapter_slug}.md").write_text(
            f"# {chapter}\n\nEnough report text for the chapter.\n", encoding="utf-8"
        )
        (self.base / "specs" / f"{chapter_slug}.md").write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n"
            "### 目的\nOpen\n### 核心结论\nX\n### 展示内容\nY\n### 证据与来源\nZ\n"
            "### 限定条件\nN\n### 报告段落映射\nMap\n### 布局意图\nLayout\n### 图标需求\n无\n"
            "## Slide 2 — Summary\n页面 ID：investment-summary-01\n页面角色：content\n"
            "### 目的\nOpen\n### 核心结论\nX\n### 展示内容\nY\n### 证据与来源\nZ\n"
            "### 限定条件\nN\n### 报告段落映射\nMap\n### 布局意图\nLayout\n### 图标需求\n无\n",
            encoding="utf-8",
        )
        (self.base / "slides" / "chapters" / f"{chapter_slug}.html").write_text(
            '<section class="slide" id="cover" data-page-role="cover"><h1>Cover</h1></section>'
            '<section class="slide" id="investment-summary-01" data-page-role="content"><h1>Summary</h1></section>',
            encoding="utf-8",
        )
        before = {
            path.relative_to(self.base).as_posix(): path.read_bytes()
            for path in self.base.rglob("*")
            if path.is_file()
        }
        preview = migrate_to_units_preview(self.base, self.chapters)
        after = {
            path.relative_to(self.base).as_posix(): path.read_bytes()
            for path in self.base.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertTrue(preview["dry_run"])
        ids = [unit["id"] for unit in preview["candidate_units"]]
        self.assertIn("cover", ids)
        self.assertIn("investment-summary-01", ids)
        self.assertTrue(any("报告单元拆分" in item["reason"] for item in preview["missing_report_mappings"]))

    def test_migrate_dry_run_reports_cross_chapter_id_conflicts(self):
        self.init_v1()
        first, second = self.chapters[0], self.chapters[1]
        for chapter, page_id in ((first, "shared-id"), (second, "shared-id")):
            (self.base / "specs" / f"{slug(chapter)}.md").write_text(
                f"## Slide 1 — {chapter}\n页面 ID：{page_id}\n页面角色：content\n",
                encoding="utf-8",
            )
            (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
                f'<section class="slide" id="{page_id}" data-page-role="content"></section>',
                encoding="utf-8",
            )
        preview = migrate_to_units_preview(self.base, self.chapters)
        self.assertFalse(preview["can_migrate"])
        self.assertTrue(any("跨章重复页面 ID" in item for item in preview["conflicts"]))

    def test_cli_units_list_and_migrate_dry_run(self):
        self.init_v1()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}

        listed = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "units", "list", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        self.assertEqual(json.loads(listed.stdout)["format_version"], "v1")

        chapter = self.chapters[0]
        (self.base / "specs" / f"{slug(chapter)}.md").write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n", encoding="utf-8"
        )
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            '<section class="slide" id="cover" data-page-role="cover"></section>', encoding="utf-8"
        )
        preview = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "migrate", "--to-units", "--dry-run", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(preview.returncode, 0, preview.stderr + preview.stdout)
        payload = json.loads(preview.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertIn("cover", payload["selected_units"])

        blocked = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "migrate", "--to-units", "--project", str(self.root)],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("正式迁移尚未实现", blocked.stderr)

    def test_dump_units_manifest_is_stable_json(self):
        units = [Unit(id="cover", chapter="投资概要", role="cover")]
        text = dump_units_manifest(units)
        payload = json.loads(text)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["units"][0]["id"], "cover")
        self.init_v1()
        with self.assertRaises(UnitsError):
            load_units_manifest(self.base, self.chapters)


if __name__ == "__main__":
    unittest.main()
