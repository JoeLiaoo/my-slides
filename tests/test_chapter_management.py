from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.chapter_management import (
    add_chapter,
    list_chapters,
    move_chapter,
    remove_chapter,
    rename_chapter,
)
from my_slides.commands.init import init_project
from my_slides.commands.status import run as status_run
from my_slides.dependencies import load_explicit_unit_deps
from my_slides.project import project_root, read_config, template_chapters
from my_slides.state import read_unit_state, refresh_unit_currency, write_unit_state
from my_slides.unit_management import add_unit
from my_slides.unit_workflow import (
    approve_unit_report,
    approve_unit_spec,
    confirm_unit_approval,
)
from my_slides.units import Unit, load_units_manifest, unit_paths, write_units_manifest
from my_slides.wiki import sync_wiki_index, validate_wiki


APPROVER = {"approved_by": "Reviewer", "approved_account": "reviewer"}


def _cli_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}


class ChapterManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "my_slides.cli", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_cli_env(),
        )

    def test_rename_chapter_updates_three_stores_and_preserves_approvals(self) -> None:
        units = self._seed_units()
        self._approve(units[1])
        before_index = (self.base / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertIn(f"## {self.chapters[0]}", before_index)
        report_sha_before = read_unit_state(self.base, "alpha")["report"].get("approved_sha256")
        spec_sha_before = read_unit_state(self.base, "alpha")["spec"].get("approved_sha256")

        result = rename_chapter(self.root, self.chapters[0], "新章节名")
        self.assertTrue(result["renamed"])
        self.assertEqual(result["to"], "新章节名")
        self.assertEqual(sorted(result["affected_units"]), ["alpha", "beta", "cover"])

        cfg = read_config(self.base / "project.yaml")
        self.assertEqual(cfg["chapters"][0], "新章节名")
        loaded, _ = load_units_manifest(self.base, chapters=None)
        self.assertEqual({unit.chapter for unit in loaded if unit.id in {"alpha", "beta", "cover"}}, {"新章节名"})
        index_text = (self.base / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertIn("## 新章节名", index_text)
        self.assertNotIn(f"## {self.chapters[0]}", index_text)
        self.assertEqual(validate_wiki(self.base, cfg), [])
        # Approvals stay bound to content; only chapter relabel changed.
        after_state = read_unit_state(self.base, "alpha")
        self.assertEqual(after_state["report"].get("approved_sha256"), report_sha_before)
        self.assertEqual(after_state["spec"].get("approved_sha256"), spec_sha_before)
        refreshed = refresh_unit_currency(
            self.base,
            Unit(id="alpha", chapter="新章节名", role="content"),
            project_root=self.root,
        )
        self.assertTrue(refreshed["report"]["current"])
        self.assertTrue(refreshed["spec"]["current"])

    def test_rename_chapter_rejects_when_units_become_invalid(self) -> None:
        self._seed_units()
        slug = self._slug_of(self.chapters[1])
        target = self._slug_of(self.chapters[0])
        # Force two chapters into the same slug by patching the config.
        cfg = read_config(self.base / "project.yaml")
        original = list(cfg["chapters"])
        cfg["chapters"] = [self.chapters[0]] + [self.chapters[1]] + [self.chapters[0]]
        (self.base / "project.yaml").write_text(
            f'project: "Demo"\nbrand_color: "#A6192E"\nsource_dirs:\n  - "."\nchapters:\n'
            + "\n".join(f'  - "{name}"' for name in cfg["chapters"])
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            rename_chapter(self.root, self.chapters[1], self.chapters[0])
        # Restore for tearDown sanity.
        (self.base / "project.yaml").write_text(
            f'project: "Demo"\nbrand_color: "#A6192E"\nsource_dirs:\n  - "."\nchapters:\n'
            + "\n".join(f'  - "{name}"' for name in original)
            + "\n",
            encoding="utf-8",
        )

    def test_remove_chapter_refuses_when_units_remain(self) -> None:
        self._seed_units()
        with self.assertRaisesRegex(ValueError, "仍有"):
            remove_chapter(self.root, self.chapters[0])

    def test_remove_chapter_succeeds_when_no_units_reference_it(self) -> None:
        self._seed_units()
        result = remove_chapter(self.root, self.chapters[1])
        self.assertTrue(result["removed"])
        cfg = read_config(self.base / "project.yaml")
        self.assertNotIn(self.chapters[1], cfg["chapters"])
        index_text = (self.base / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertNotIn(f"## {self.chapters[1]}", index_text)
        self.assertEqual(validate_wiki(self.base, cfg), [])

    def test_add_chapter_appends_and_inserts_with_after(self) -> None:
        self._seed_units()
        append = add_chapter(self.root, "追加章节")
        self.assertEqual(append["position"], len(self.chapters))
        cfg = read_config(self.base / "project.yaml")
        self.assertEqual(cfg["chapters"][-1], "追加章节")
        index_text = (self.base / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertIn("## 追加章节", index_text)

        insert = add_chapter(self.root, "首插章节", after=self.chapters[0])
        cfg = read_config(self.base / "project.yaml")
        self.assertEqual(cfg["chapters"][cfg["chapters"].index("首插章节") - 1], self.chapters[0])
        index_text = (self.base / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertIn("## 首插章节", index_text)

    def test_move_chapter_reorders_yaml_wiki_and_keeps_units_valid(self) -> None:
        self._seed_units()
        move_chapter(self.root, self.chapters[0], before=self.chapters[2])
        cfg = read_config(self.base / "project.yaml")
        new_order = cfg["chapters"]
        self.assertEqual(new_order.index(self.chapters[0]), new_order.index(self.chapters[2]) - 1)
        index_lines = [
            line.strip() for line in (self.base / "wiki" / "index.md").read_text(encoding="utf-8").splitlines()
        ]
        all_headings = [line for line in index_lines if line.startswith("## ")]
        chapter_headings = [line for line in all_headings if line != "## 补充研究"]
        self.assertEqual(chapter_headings, [f"## {name}" for name in new_order])
        loaded, errors = load_units_manifest(self.base, cfg["chapters"])
        self.assertEqual(errors, [])

    def test_chapters_list_reports_units_per_chapter_and_orphans(self) -> None:
        units = self._seed_units()
        snapshot = list_chapters(self.base, self.chapters, units)
        self.assertEqual(snapshot["count"], len(self.chapters))
        self.assertEqual(snapshot["chapters"][0]["unit_count"], 3)
        self.assertEqual(snapshot["chapters"][0]["unit_ids"], ["cover", "alpha", "beta"])
        self.assertEqual(snapshot["orphan_chapters"], [])

        # Force an orphan by editing units.json outside the CLI.
        payload = json.loads((self.base / "units.json").read_text(encoding="utf-8"))
        payload["units"][1]["chapter"] = "丢失章节"
        (self.base / "units.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshot = list_chapters(self.base, self.chapters, None)
        self.assertEqual(snapshot["orphan_chapters"], ["丢失章节"])

    def test_cli_rename_then_doctor_passes_and_wiki_synced(self) -> None:
        units = self._seed_units()
        self._approve(units[1])
        rename = self.cli(
            "chapters", "rename", self.chapters[0], "新章节名",
            "--project", str(self.root), "--json",
        )
        self.assertEqual(rename.returncode, 0, rename.stderr + rename.stdout)
        payload = json.loads(rename.stdout)
        self.assertEqual(payload["from"], self.chapters[0])
        self.assertEqual(payload["to"], "新章节名")
        doctor = self.cli("doctor", "--project", str(self.root), "--json")
        self.assertEqual(doctor.returncode, 0, doctor.stderr + doctor.stdout)
        doctor_payload = json.loads(doctor.stdout)
        self.assertTrue(doctor_payload["ok"])
        validate_wiki(self.base, read_config(self.base / "project.yaml"))
        self.assertEqual(validate_wiki(self.base, read_config(self.base / "project.yaml")), [])

    def test_cli_chapters_remove_then_status_lists_changes(self) -> None:
        self._seed_units()
        cfg = read_config(self.base / "project.yaml")
        empty_chapter = cfg["chapters"][-1]
        result = self.cli(
            "chapters", "remove", empty_chapter,
            "--project", str(self.root), "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        cfg_after = read_config(self.base / "project.yaml")
        self.assertNotIn(empty_chapter, cfg_after["chapters"])

    # --- helpers ---

    def _slug_of(self, value: str) -> str:
        from my_slides.units import slug

        return slug(value)

    def _seed_units(self) -> list[Unit]:
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="alpha", chapter=self.chapters[0], role="content"),
            Unit(id="beta", chapter=self.chapters[0], role="content"),
        ]
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            paths.report.parent.mkdir(parents=True, exist_ok=True)
            paths.spec.parent.mkdir(parents=True, exist_ok=True)
            paths.page.parent.mkdir(parents=True, exist_ok=True)
            paths.report.write_text(
                f"# {unit.id}\n\nDetailed, evidence-backed analysis for {unit.id}. " * 3,
                encoding="utf-8",
            )
            paths.spec.write_text(self._spec_text(unit), encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" id="{unit.id}" data-unit-id="{unit.id}" '
                f'data-page-role="{unit.role}"></section>',
                encoding="utf-8",
            )
        return units

    def _spec_text(self, unit: Unit) -> str:
        return (
            f"## Slide 1 — {unit.id}\n单元 ID：{unit.id}\n页面角色：{unit.role}\n"
            "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
            "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
            "### 布局意图\nLayout.\n### 图标需求\n无\n"
        )

    def _approve(self, unit: Unit) -> None:
        approve_unit_report(self.base, unit, when="t1", project_root=self.root, **APPROVER)
        approve_unit_spec(self.base, unit, when="t2", project_root=self.root, **APPROVER)


if __name__ == "__main__":
    unittest.main()
