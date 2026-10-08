import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.cli import approve_revision, init_project, slug, template_chapters
from my_slides.units import (
    UnitsError,
    assemble_report,
    detect_format_version,
    dump_units_manifest,
    list_units_status,
    load_units_manifest,
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
        units = self.base / "units.json"
        if units.exists():
            units.unlink()
        (self.base / "slides" / "chapters").mkdir(parents=True, exist_ok=True)

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

    def test_cli_units_list_refuses_v1_without_units_json(self):
        self.init_v1()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}

        listed = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "units", "list", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(listed.returncode, 2, listed.stderr + listed.stdout)
        error = json.loads(listed.stdout).get("error", "")
        self.assertIn("units.json", error)
        self.assertIn("迁移", error)

        # migrate command is removed
        missing = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "migrate", "--to-units", "--dry-run", "--project", str(self.root)],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertTrue(
            "invalid choice" in missing.stderr.lower()
            or "unrecognized" in missing.stderr.lower()
            or "migrate" in missing.stderr.lower(),
            missing.stderr,
        )

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
        # Unit-level approve is supported; chapter digests must not look "current".
        self.assertTrue(payload["approvals"]["report"]["supported"])
        self.assertIn("--unit", payload["approvals"]["report"]["message"])
        approve_cli = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "approve", "report", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(approve_cli.returncode, 2, approve_cli.stderr + approve_cli.stdout)
        approve_payload = json.loads(approve_cli.stdout)
        self.assertIn("v2", approve_payload.get("error", ""))

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
