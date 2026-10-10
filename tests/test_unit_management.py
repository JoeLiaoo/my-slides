from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.dependencies import load_explicit_unit_deps
from my_slides.project import template_chapters
from my_slides.state import refresh_unit_currency, read_unit_state, write_unit_state
from my_slides.unit_management import (
    add_unit,
    list_trash,
    move_unit,
    remove_plan,
    remove_unit,
    rename_unit,
    restore_unit,
)
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec, confirm_unit_approval
from my_slides.units import Unit, list_units_status, unit_paths, write_units_manifest


APPROVER = {"approved_by": "Reviewer", "approved_account": "reviewer"}


def spec_text(unit: Unit) -> str:
    return (
        f"## Slide 1 — {unit.id}\n页面 ID：{unit.id}\n页面角色：{unit.role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\nLayout.\n### 图标需求\n无\n"
    )


class UnitManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def tearDown(self):
        self.temp.cleanup()

    def setup_units(self, ids: list[tuple[str, int, str]]):
        units = [Unit(id=unit_id, chapter=self.chapters[chapter], role=role) for unit_id, chapter, role in ids]
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            paths.report.parent.mkdir(parents=True, exist_ok=True)
            paths.spec.parent.mkdir(parents=True, exist_ok=True)
            paths.page.parent.mkdir(parents=True, exist_ok=True)
            paths.report.write_text(f"# {unit.id}\n\n" + f"Detailed, evidence-backed analysis for {unit.id}. " * 3, encoding="utf-8")
            paths.spec.write_text(spec_text(unit), encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" id="{unit.id}" data-unit-id="{unit.id}" data-page-role="{unit.role}"></section>',
                encoding="utf-8",
            )
        return units

    def approve(self, unit: Unit, *, spec: bool = True):
        approve_unit_report(self.base, unit, when="t1", project_root=self.root, **APPROVER)
        if spec:
            approve_unit_spec(self.base, unit, when="t2", project_root=self.root, **APPROVER)

    def cli(self, *arguments: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        return subprocess.run(
            [sys.executable, "-m", "my_slides.cli", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    def test_add_places_unit_and_creates_visible_skeletons(self):
        self.setup_units([("cover", 0, "cover"), ("second", 1, "content")])
        result = add_unit(self.base, "new-unit", self.chapters[0], self.chapters, after="cover")
        units, _ = __import__("my_slides.units", fromlist=["load_units_manifest"]).load_units_manifest(self.base, self.chapters)
        self.assertEqual([unit.id for unit in units], ["cover", "new-unit", "second"])
        self.assertIn("TODO", unit_paths(self.base, "new-unit").report.read_text(encoding="utf-8"))
        self.assertEqual(result["position"], 1)

    def test_remove_defaults_to_preview_then_trash_restore_preserves_approvals_and_position(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 0, "content")])
        self.approve(units[1])
        before = (self.base / "units.json").read_bytes()
        plan = remove_plan(self.base, "alpha", self.chapters)
        self.assertTrue(plan["requires_user_consent"])
        self.assertEqual((self.base / "units.json").read_bytes(), before)
        self.assertTrue(unit_paths(self.base, "alpha").report.is_file())

        removed = remove_unit(self.base, "alpha", self.chapters)
        self.assertTrue(removed["removed"])
        self.assertFalse(unit_paths(self.base, "alpha").report.exists())
        self.assertIn("alpha", removed["restore_command"])
        self.assertEqual(len(list_trash(self.base)), 1)

        restored = restore_unit(self.base, removed["trash_id"], self.chapters)
        self.assertEqual(restored["position"], 1)
        self.assertTrue(restored["approvals"]["report"])
        self.assertTrue(restored["approvals"]["spec"])
        self.assertEqual([row["id"] for row in list_units_status(self.base, self.chapters)["units"]], ["cover", "alpha", "beta"])
        self.assertEqual(list_trash(self.base), [])

    def test_remove_blocks_inbound_unit_and_markdown_references(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 0, "content")])
        sidecar = unit_paths(self.base, "beta").report.with_name("beta.depends-on.json")
        sidecar.write_text(json.dumps(["alpha"]), encoding="utf-8")
        unit_paths(self.base, "beta").report.write_text(
            unit_paths(self.base, "beta").report.read_text(encoding="utf-8") + "\n[Alpha](../../reports/units/alpha.md)\n",
            encoding="utf-8",
        )
        plan = remove_plan(self.base, "alpha", self.chapters)
        self.assertTrue(plan["blocked"])
        self.assertEqual(plan["dependencies"]["dependent_units"], ["beta"])
        self.assertEqual(plan["dependencies"]["markdown_references"], ["reports/units/beta.md"])
        with self.assertRaisesRegex(ValueError, "无法删除"):
            remove_unit(self.base, "alpha", self.chapters)

    def test_external_markdown_reference_is_listed_and_blocks_rename_without_editing_source(self):
        self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content")])
        source = self.root / "source-notes.md"
        source.write_text("[Alpha](my-slides/reports/units/alpha.md)\n", encoding="utf-8")
        plan = remove_plan(self.base, "alpha", self.chapters, project_root=self.root)
        self.assertEqual(plan["dependencies"]["markdown_references"], ["source-notes.md"])
        self.assertEqual(plan["dependencies"]["external_markdown_references"], ["source-notes.md"])
        with self.assertRaisesRegex(ValueError, "工作区外"):
            rename_unit(self.base, "alpha", "renamed-alpha", self.chapters)
        self.assertIn("my-slides/reports/units/alpha.md", source.read_text(encoding="utf-8"))

    def test_cross_chapter_move_reconfirms_only_report_and_keeps_unchanged_spec(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 1, "content")])
        self.approve(units[1])
        moved = move_unit(self.base, "alpha", self.chapters, after="beta", chapter=self.chapters[1])
        self.assertEqual(moved["report_reconfirmation"], f"章节：{self.chapters[0]} → {self.chapters[1]}，内容未变")
        state = refresh_unit_currency(self.base, Unit(id="alpha", chapter=self.chapters[1], role="content"), project_root=self.root)
        self.assertFalse(state["report"]["current"])
        self.assertTrue(state["report"]["pending_current"])
        self.assertTrue(state["spec"]["current"])
        confirmed = confirm_unit_approval(
            self.base,
            Unit(id="alpha", chapter=self.chapters[1], role="content"),
            "report",
            when="t3",
            approved_by="Reviewer 2",
            approved_account="reviewer2",
            project_root=self.root,
        )
        self.assertTrue(confirmed["report"]["current"])
        self.assertTrue(confirmed["spec"]["current"])

    def test_cross_chapter_move_does_not_create_context_only_approval_for_unapproved_report(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 1, "content")])
        moved = move_unit(self.base, "alpha", self.chapters, after="beta", chapter=self.chapters[1])
        self.assertIsNone(moved["report_reconfirmation"])
        state = refresh_unit_currency(self.base, Unit(id="alpha", chapter=self.chapters[1], role="content"), project_root=self.root)
        self.assertFalse(state["report"]["current"])
        self.assertFalse(state["report"]["pending_current"])

    def test_rename_never_revives_a_stale_approval(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content")])
        self.approve(units[1])
        report = unit_paths(self.base, "alpha").report
        report.write_text(report.read_text(encoding="utf-8") + "\nSubstantive revision.\n", encoding="utf-8")
        renamed = Unit(id="renamed-alpha", chapter=self.chapters[0], role="content")
        rename_unit(self.base, "alpha", "renamed-alpha", self.chapters)
        self.assertFalse(refresh_unit_currency(self.base, renamed, project_root=self.root)["report"]["current"])

    def test_move_appends_to_an_empty_chapter_and_before_places_first(self):
        from my_slides.units import load_units_manifest

        self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 0, "content")])
        empty_chapter = self.chapters[2]
        appended = move_unit(self.base, "alpha", self.chapters, chapter=empty_chapter)
        units, errors = load_units_manifest(self.base, self.chapters)
        self.assertEqual(errors, [])
        self.assertEqual(appended["to"]["chapter"], empty_chapter)
        self.assertEqual([unit.id for unit in units if unit.chapter == empty_chapter], ["alpha"])
        move_unit(self.base, "beta", self.chapters, before="alpha", chapter=empty_chapter)
        units, _errors = load_units_manifest(self.base, self.chapters)
        self.assertEqual([unit.id for unit in units if unit.chapter == empty_chapter], ["beta", "alpha"])
        with self.assertRaisesRegex(ValueError, "目标章节"):
            move_unit(self.base, "beta", self.chapters, before="cover")

    def test_same_chapter_reorder_preserves_approvals_but_invalidates_checks(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 0, "content")])
        self.approve(units[1])
        state = read_unit_state(self.base, "alpha")
        state["check"].update({"result": "pass", "input_fingerprint": "old-check", "current": True})
        write_unit_state(self.base, "alpha", state)
        move_unit(self.base, "alpha", self.chapters, after="beta")
        after = refresh_unit_currency(self.base, units[1], project_root=self.root)
        self.assertTrue(after["report"]["current"])
        self.assertTrue(after["spec"]["current"])
        self.assertFalse(after["check"]["current"])
        self.assertIsNone(after["check"]["input_fingerprint"])

    def test_rename_rewrites_identity_links_and_dependencies_and_rebinds_approvals(self):
        units = self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content"), ("beta", 0, "content")])
        beta_report = unit_paths(self.base, "beta").report
        beta_report.write_text(
            beta_report.read_text(encoding="utf-8")
            + "\n[Alpha report](../../reports/units/alpha.md#evidence)\n\n"
            + "[AlphaRef]: ../../reports/units/alpha.md \"approved unit\"\nSee [the report][AlphaRef].\n\n"
            + "```md\n[example](../../reports/units/alpha.md)\n```\n",
            encoding="utf-8",
        )
        sidecar = beta_report.with_name("beta.depends-on.json")
        sidecar.write_text(json.dumps(["alpha"]), encoding="utf-8")
        self.approve(units[1])
        self.approve(units[2], spec=False)

        result = rename_unit(self.base, "alpha", "renamed-alpha", self.chapters)
        renamed = Unit(id="renamed-alpha", chapter=self.chapters[0], role="content")
        self.assertTrue(result["report_approval_preserved"])
        self.assertTrue(result["spec_approval_preserved"])
        self.assertTrue(refresh_unit_currency(self.base, renamed, project_root=self.root)["spec"]["current"])
        self.assertTrue(refresh_unit_currency(self.base, units[2], project_root=self.root)["report"]["current"])
        spec = unit_paths(self.base, "renamed-alpha").spec.read_text(encoding="utf-8")
        page = unit_paths(self.base, "renamed-alpha").page.read_text(encoding="utf-8")
        self.assertIn("页面 ID：renamed-alpha", spec)
        self.assertIn('data-unit-id="renamed-alpha"', page)
        self.assertEqual(load_explicit_unit_deps(self.base, "beta"), ["renamed-alpha"])
        content = beta_report.read_text(encoding="utf-8")
        self.assertIn("(renamed-alpha.md#evidence)", content)
        self.assertIn("[AlphaRef]: renamed-alpha.md \"approved unit\"", content)
        self.assertIn("[example](../../reports/units/alpha.md)", content)

    def test_trash_restore_refuses_path_collision_and_lists_orphans_not_trash(self):
        self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content")])
        removed = remove_unit(self.base, "alpha", self.chapters)
        orphan = self.base / "reports" / "units" / "ghost.md"
        orphan.write_text("stray", encoding="utf-8")
        hidden = self.base / ".state" / "trash" / "other" / "reports" / "units" / "invisible.md"
        hidden.parent.mkdir(parents=True, exist_ok=True)
        hidden.write_text("trash", encoding="utf-8")
        self.assertEqual([item["id"] for item in list_units_status(self.base, self.chapters)["orphaned"]], ["ghost"])
        doctor = self.cli("doctor", "--project", str(self.root), "--json")
        self.assertEqual(doctor.returncode, 1, doctor.stderr + doctor.stdout)
        self.assertEqual(json.loads(doctor.stdout)["orphaned"][0]["id"], "ghost")
        unit_paths(self.base, "alpha").report.parent.mkdir(parents=True, exist_ok=True)
        unit_paths(self.base, "alpha").report.write_text("replacement", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "恢复目标已存在"):
            restore_unit(self.base, removed["trash_id"], self.chapters)

    def test_cli_remove_json_is_preview_until_yes_and_trash_commands_work(self):
        self.setup_units([("cover", 0, "cover"), ("alpha", 0, "content")])
        preview = self.cli("units", "remove", "alpha", "--project", str(self.root), "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr + preview.stdout)
        preview_data = json.loads(preview.stdout)
        self.assertFalse(preview_data["executed"])
        self.assertTrue(preview_data["artifacts"])
        self.assertTrue(unit_paths(self.base, "alpha").report.is_file())

        removed = self.cli("units", "remove", "alpha", "--yes", "--project", str(self.root), "--json")
        self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)
        result = json.loads(removed.stdout)
        self.assertTrue(result["executed"])
        self.assertIn("units restore", result["restore_command"])

        listed = self.cli("units", "trash", "list", "--project", str(self.root), "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        self.assertEqual(listed.stdout and len(json.loads(listed.stdout)["trash"]), 1)
        restored = self.cli("units", "restore", result["trash_id"], "--project", str(self.root), "--json")
        self.assertEqual(restored.returncode, 0, restored.stderr + restored.stdout)
        self.assertTrue(json.loads(restored.stdout)["restored"])

    def test_cli_assemble_rejects_manifest_chapter_outside_project_config(self):
        write_units_manifest(self.base, [Unit(id="cover", chapter="Not configured", role="cover")])
        result = self.cli("assemble", "--project", str(self.root), "--json")
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn("章节不存在", json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
