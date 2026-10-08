import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.cli import approve_revision, init_project, slug, template_chapters
from my_slides.cli import SlideFragmentParser
from my_slides.units import (
    UNIT_ID_RE,
    UnitsError,
    assemble_report,
    detect_format_version,
    dump_units_manifest,
    list_units_status,
    load_units_manifest,
    migrate_to_units_preview,
    resolve_local_markdown_path,
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
        self.assertTrue(preview["preview_ok"])
        ids = [unit["id"] for unit in preview["candidate_units"]]
        self.assertIn("cover", ids)
        self.assertIn("investment-summary-01", ids)
        self.assertTrue(any("报告单元拆分" in item["reason"] for item in preview["missing_report_mappings"]))
        # Mapping gaps block migration even when the dry-run itself succeeds.
        self.assertFalse(preview["can_migrate"])
        self.assertIn("cover", preview["blocked_units"])

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
        self.assertTrue(payload["preview_ok"])
        self.assertIn("cover", payload["selected_units"])
        # Preview success is not the same as ready-to-migrate.
        self.assertFalse(payload["can_migrate"])

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

    def test_v2_refuses_legacy_approve_and_status_does_not_reuse_chapter_approval(self):
        self.init_v1()
        cfg = {"chapters": self.chapters, "source_dirs": ["."]}
        for chapter in self.chapters:
            (self.base / "reports" / f"{slug(chapter)}.md").write_text(
                f"# {chapter}\n\n" + "Evidence-backed report text. " * 4, encoding="utf-8"
            )
        digest, errors = approve_revision(self.base, cfg, "report")
        self.assertEqual(errors, [])
        self.assertTrue(digest)
        # Switch to v2 without creating report units — legacy approve must not succeed.
        write_units_manifest(self.base, [Unit(id="cover", chapter=self.chapters[0], role="cover")])
        refused, refuse_errors = approve_revision(self.base, cfg, "report")
        self.assertIsNone(refused)
        self.assertTrue(any("v2" in error for error in refuse_errors), refuse_errors)

        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        status = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "status", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["format_version"], "v2")
        self.assertFalse(payload["approvals"]["report"]["current"])
        self.assertFalse(payload["approvals"]["report"]["supported"])
        approve_cli = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "approve", "report", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(approve_cli.returncode, 2, approve_cli.stderr + approve_cli.stdout)
        approve_payload = json.loads(approve_cli.stdout)
        self.assertIn("v2", approve_payload.get("error", ""))

    def test_migrate_fallback_ids_are_ascii_and_validated(self):
        self.init_v1()
        for chapter in self.chapters:
            (self.base / "reports" / f"{slug(chapter)}.md").write_text(
                f"# {chapter}\n\nEnough report text for the chapter.\n", encoding="utf-8"
            )
        preview = migrate_to_units_preview(self.base, self.chapters)
        self.assertTrue(preview["preview_ok"])
        ids = [unit["id"] for unit in preview["candidate_units"]]
        self.assertEqual(ids[0], "cover")
        for unit_id in ids:
            self.assertRegex(unit_id, UNIT_ID_RE.pattern, unit_id)
            self.assertNotRegex(unit_id, r"[\u3400-\u9fff]")
        self.assertTrue(any(unit_id.startswith("chapter-") for unit_id in ids[1:]), ids)
        self.assertFalse(any("候选单元 ID 非法" in item for item in preview["conflicts"]))

    def test_missing_report_mappings_block_can_migrate_but_preview_ok(self):
        self.init_v1()
        chapter = self.chapters[0]
        (self.base / "specs" / f"{slug(chapter)}.md").write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n"
            "## Slide 2 — Summary\n页面 ID：investment-summary-01\n页面角色：content\n",
            encoding="utf-8",
        )
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            '<section class="slide" id="cover" data-page-role="cover"></section>'
            '<section class="slide" id="investment-summary-01" data-page-role="content"></section>',
            encoding="utf-8",
        )
        preview = migrate_to_units_preview(self.base, self.chapters)
        self.assertTrue(preview["preview_ok"])
        self.assertFalse(preview["can_migrate"])
        self.assertTrue(preview["missing_report_mappings"])
        self.assertTrue(preview["blocked_units"])
        self.assertEqual(preview["conflicts"], [])

    def test_assemble_report_preserves_percent_encoded_path_chars(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        self.write_v2(
            units,
            reports={
                "cover": "# Cover\n\nOpening.\n",
                "summary-01": (
                    "# Summary\n\n"
                    "See [round](../../wiki/round%231.md#section) and "
                    "[notes](../../wiki/my%20notes.md).\n"
                ),
            },
        )
        (self.base / "wiki" / "round#1.md").write_text("# Round\n", encoding="utf-8")
        (self.base / "wiki" / "my notes.md").write_text("# Notes\n", encoding="utf-8")
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [])
        self.assertIn("[round](../wiki/round%231.md#section)", document)
        self.assertIn("[notes](../wiki/my%20notes.md)", document)
        self.assertNotIn("../wiki/round#1.md", document)
        self.assertNotIn("../wiki/my notes.md", document)

    def test_empty_manifest_does_not_overwrite_existing_report(self):
        units = [Unit(id="cover", chapter=self.chapters[0], role="cover")]
        self.write_v2(units, reports={"cover": "# Cover\n\nKeep me.\n"})
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [])
        report = self.base / "reports" / "report.md"
        original = report.read_text(encoding="utf-8")
        self.assertIn("Keep me", original)
        # Empty manifest must fail validation and leave the assembled report untouched.
        (self.base / "units.json").write_text(
            json.dumps({"schema_version": 2, "units": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        failed, fail_errors = assemble_report(self.base, write=True)
        self.assertEqual(failed, "")
        self.assertTrue(any("至少需要一个单元" in error for error in fail_errors), fail_errors)
        self.assertEqual(report.read_text(encoding="utf-8"), original)

        # Duplicate IDs / cover-not-first also keep the original report.
        (self.base / "units.json").write_text(
            json.dumps({
                "schema_version": 2,
                "units": [
                    {"id": "body-01", "chapter": self.chapters[0], "role": "content"},
                    {"id": "body-01", "chapter": self.chapters[0], "role": "cover"},
                ],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        failed, fail_errors = assemble_report(self.base, write=True)
        self.assertEqual(failed, "")
        self.assertTrue(any("重复" in error or "cover" in error for error in fail_errors), fail_errors)
        self.assertEqual(report.read_text(encoding="utf-8"), original)

    def test_cover_not_first_blocks_can_migrate(self):
        self.init_v1()
        first, second = self.chapters[0], self.chapters[1]
        (self.base / "reports" / f"{slug(first)}.md").write_text(
            f"# {first}\n\nEnough report text for the chapter.\n", encoding="utf-8"
        )
        (self.base / "reports" / f"{slug(second)}.md").write_text(
            f"# {second}\n\nEnough report text for the chapter.\n", encoding="utf-8"
        )
        (self.base / "specs" / f"{slug(first)}.md").write_text(
            "## Slide 1 — Body\n页面 ID：body-01\n页面角色：content\n", encoding="utf-8"
        )
        (self.base / "specs" / f"{slug(second)}.md").write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n", encoding="utf-8"
        )
        (self.base / "slides" / "chapters" / f"{slug(first)}.html").write_text(
            '<section class="slide" id="body-01" data-page-role="content"></section>', encoding="utf-8"
        )
        (self.base / "slides" / "chapters" / f"{slug(second)}.html").write_text(
            '<section class="slide" id="cover" data-page-role="cover"></section>', encoding="utf-8"
        )
        preview = migrate_to_units_preview(self.base, [first, second])
        self.assertTrue(preview["preview_ok"])
        self.assertFalse(preview["can_migrate"])
        self.assertTrue(any("首位" in item for item in preview["conflicts"]), preview["conflicts"])

    def test_assemble_rewrites_reference_style_links_and_validates(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        (self.root / "bp.md").write_text("# Business plan\n", encoding="utf-8")
        self.write_v2(
            units,
            reports={
                "cover": "# Cover\n\nOpening.\n",
                "summary-01": (
                    "# Summary\n\n"
                    "See [来源][bp] for details.\n\n"
                    "[bp]: ../../../bp.md\n"
                ),
            },
        )
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [])
        self.assertIn("[来源][bp]", document)
        self.assertIn("[bp]: ../../bp.md", document)
        self.assertNotIn("[bp]: ../../../bp.md", document)

        # Broken reference definition must fail assemble and keep prior report.
        report = self.base / "reports" / "report.md"
        original = report.read_text(encoding="utf-8")
        unit_paths(self.base, "summary-01").report.write_text(
            "# Summary\n\nSee [来源][bp].\n\n[bp]: ../../../missing-bp.md\n",
            encoding="utf-8",
        )
        failed, fail_errors = assemble_report(self.base, units, write=True)
        self.assertEqual(failed, "")
        self.assertTrue(any("本地链接失效" in error for error in fail_errors), fail_errors)
        self.assertEqual(report.read_text(encoding="utf-8"), original)

    def test_v2_project_migrate_preview_does_not_list_noop_as_conflict(self):
        units = [Unit(id="cover", chapter=self.chapters[0], role="cover")]
        self.write_v2(units)
        preview = migrate_to_units_preview(self.base, self.chapters)
        self.assertEqual(preview["format_version"], "v2")
        self.assertFalse(preview["can_migrate"])
        self.assertEqual(preview["conflicts"], [])
        self.assertTrue(any("无需迁移" in item for item in preview["warnings"]))

    def test_migrate_html_boundaries_match_slide_fragment_parser(self):
        self.init_v1()
        chapter = self.chapters[0]
        # Unclosed <p> previously made the migrate preview under-count slides vs merge.
        html = (
            '<section class="slide" id="cover" data-page-role="cover"><p>unclosed'
            '<script type="application/json" class="slide-notes">'
            '{"title":"Cover","script":"Hi","notes":[]}</script></section>'
            '<section class="slide" id="summary-01" data-page-role="content"><h1>Summary</h1>'
            '<script type="application/json" class="slide-notes">'
            '{"title":"Summary","script":"Hi","notes":[]}</script></section>'
        )
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(html, encoding="utf-8")
        (self.base / "specs" / f"{slug(chapter)}.md").write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n"
            "## Slide 2 — Summary\n页面 ID：summary-01\n页面角色：content\n",
            encoding="utf-8",
        )
        (self.base / "reports" / f"{slug(chapter)}.md").write_text(
            f"# {chapter}\n\nEnough report text for the chapter.\n", encoding="utf-8"
        )
        parser = SlideFragmentParser()
        parser.feed(html)
        parser.close()
        preview = migrate_to_units_preview(self.base, [chapter])
        boundary = preview["html_boundaries"][0]
        self.assertEqual(len(parser.slides), 2)
        self.assertEqual(boundary["slide_count"], len(parser.slides))
        self.assertEqual([slide["id"] for slide in boundary["slides"]], ["cover", "summary-01"])
        # build_slides uses the same parser; slide list length matches even when nesting warns.
        self.assertEqual(len(parser.slides), 2)

    def test_shared_local_link_resolution_matches_percent_encoding(self):
        self.init_v1()
        report = self.base / "reports" / f"{slug(self.chapters[0])}.md"
        target = self.base / "wiki" / "my notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        encoded = resolve_local_markdown_path("../wiki/my%20notes.md", report)
        literal = resolve_local_markdown_path("../wiki/my notes.md", report)
        self.assertEqual(encoded, target.resolve())
        self.assertEqual(literal, target.resolve())

    def test_assemble_skips_footnotes_and_accepts_titled_links(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        wiki = self.base  # written after write_v2 creates tree
        self.write_v2(
            units,
            reports={
                "cover": "# Cover\n\nOpening.\n",
                "summary-01": "# Summary\n\nplaceholder\n",
            },
        )
        company = self.base / "wiki" / "a.md"
        company.write_text("# Company\n", encoding="utf-8")
        unit_paths(self.base, "summary-01").report.write_text(
            "# Summary\n\n"
            "见[公司](../../wiki/a.md \"公司页\")与脚注[^1]。\n\n"
            "[^1]: 来自管理层访谈，2024 年\n\n"
            "示例：`[假](../../wiki/missing.md)`\n",
            encoding="utf-8",
        )
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [], errors)
        self.assertIn("公司页", document)
        self.assertIn("[^1]:", document)


if __name__ == "__main__":
    unittest.main()
