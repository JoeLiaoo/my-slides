from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.delivery import (
    DELIVERY_FILENAME_RE,
    export_delivery,
    last_delivery,
    list_deliveries,
    units_changed_since,
)
from my_slides.project import read_config, template_chapters
from my_slides.state import read_unit_state, write_unit_state
from my_slides.units import Unit, unit_paths, write_units_manifest


def _spec_text(unit: Unit) -> str:
    return (
        f"## Slide 1 — {unit.id}\n单元 ID：{unit.id}\n页面角色：{unit.role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\n#### 读者问题\nQ.\n#### 唯一结论\nA.\n#### 关系类型\nType.\n#### 主视觉\nChart.\n#### 阅读顺序\nOrder.\n#### 选这个形式的原因\nReason.\n### 图标需求\n无\n"
    )


def _approve_everything(base: Path, units: list[Unit], project_root: Path) -> None:
    """Mark report, Spec, HTML, and browser check current for every unit."""
    from my_slides.dependencies import fingerprint_file
    from my_slides.state import check_input_fingerprint
    from my_slides.theme import shell_fingerprint
    from my_slides.unit_workflow import approve_unit_report, approve_unit_spec

    deck_path = base / "slides" / "index.html"
    deck_sha = fingerprint_file(deck_path) if deck_path.is_file() else None
    for unit in units:
        approve_unit_report(
            base, unit, when="2024-01-01T00:00:00",
            approved_by="Reviewer", approved_account="reviewer", project_root=project_root,
        )
        approve_unit_spec(
            base, unit, when="2024-01-01T00:00:00",
            approved_by="Reviewer", approved_account="reviewer", project_root=project_root,
        )
        state = read_unit_state(base, unit.id)
        paths = unit_paths(base, unit.id)
        page_sha = fingerprint_file(paths.page)
        spec_sha = state["spec"]["approved_sha256"]
        state["html"] = {
            "content_sha256": page_sha,
            "spec_sha256": spec_sha,
            "build_sha256": page_sha,
            "shell_fingerprint": shell_fingerprint(),
            "current": True,
        }
        state["check"] = {
            "result": "pass",
            "input_fingerprint": check_input_fingerprint(page_sha, spec_sha, deck_sha=deck_sha),
            "current": True,
        }
        write_unit_state(base, unit.id, state)


class ExportDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *arguments: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        return subprocess.run(
            [sys.executable, "-m", "my_slides.cli", *arguments],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )

    def _seed(self) -> list[Unit]:
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="alpha", chapter=self.chapters[0], role="content"),
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
            paths.spec.write_text(_spec_text(unit), encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" id="{unit.id}" data-unit-id="{unit.id}" '
                f'data-page-role="{unit.role}"></section>',
                encoding="utf-8",
            )
        return units

    def _deck(self, content: str = "<!doctype html><html><body>deck</body></html>") -> None:
        self.base.joinpath("slides").mkdir(parents=True, exist_ok=True)
        (self.base / "slides" / "index.html").write_text(content, encoding="utf-8")

    def test_export_records_named_file_and_appends_to_deliveries(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")

        record = export_delivery(self.base, cfg, project_root=self.root)
        today = datetime.date.today().strftime("%Y-%m-%d")
        match = DELIVERY_FILENAME_RE.fullmatch(record["file"])
        self.assertIsNotNone(match, record["file"])
        self.assertEqual(match.group("date"), today)
        self.assertEqual(match.group("sequence"), "1")
        self.assertTrue((self.root / record["file"]).is_file())

        deliveries = list_deliveries(self.base)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["date"], today)
        self.assertEqual(deliveries[0]["sequence"], 1)
        self.assertEqual({item["id"] for item in deliveries[0]["units"]}, {"cover", "alpha"})

    def test_export_increments_sequence_within_same_day(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")

        first = export_delivery(self.base, cfg, project_root=self.root)
        second = export_delivery(self.base, cfg, project_root=self.root)
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        self.assertNotEqual(first["file"], second["file"])

    def test_export_refuses_when_state_not_current(self) -> None:
        units = self._seed()
        self._deck()
        cfg = read_config(self.base / "project.yaml")
        with self.assertRaisesRegex(ValueError, "交付前需要补齐"):
            export_delivery(self.base, cfg, project_root=self.root)

    def test_export_refuses_when_deck_missing(self) -> None:
        units = self._seed()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")
        with self.assertRaisesRegex(ValueError, "slides/index.html"):
            export_delivery(self.base, cfg, project_root=self.root)

    def test_export_honors_output_dir(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")

        target = self.root / "exports"
        record = export_delivery(self.base, cfg, project_root=self.root, output_dir=target)
        self.assertTrue((target / record["file"]).is_file())

    def test_status_shows_last_delivery_and_changes_since(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")
        export_delivery(self.base, cfg, project_root=self.root)

        # Change a unit and re-check that status reports it as changed since delivery.
        report = unit_paths(self.base, "alpha").report
        report.write_text(report.read_text(encoding="utf-8") + "\n追加一句话。\n", encoding="utf-8")
        _approve_everything(self.base, units, self.root)

        result = self.cli("status", "--project", str(self.root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["delivery"]["has_delivery"])
        self.assertEqual(payload["delivery"]["last_delivery"]["sequence"], 1)
        changed_units = [item["unit"] for item in payload["delivery"]["changed_since"]]
        self.assertIn("alpha", changed_units)
        self.assertNotIn("cover", changed_units)

    def test_units_changed_since_lists_missing_units(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        cfg = read_config(self.base / "project.yaml")
        export_delivery(self.base, cfg, project_root=self.root)
        # Drop alpha; report it as missing from delivery.
        remaining = [unit for unit in units if unit.id == "cover"]
        write_units_manifest(self.base, remaining)
        delta = units_changed_since(self.base, self.root)
        self.assertEqual(delta["missing_units"], ["alpha"])

    def test_cli_two_exports_are_distinguishable(self) -> None:
        units = self._seed()
        self._deck()
        _approve_everything(self.base, units, self.root)
        first = self.cli("export", "--project", str(self.root), "--json")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        second = self.cli("export", "--project", str(self.root), "--json")
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        first_payload = json.loads(first.stdout)
        second_payload = json.loads(second.stdout)
        self.assertNotEqual(first_payload["file"], second_payload["file"])
        self.assertNotEqual(first_payload["sequence"], second_payload["sequence"])
        self.assertTrue((self.root / first_payload["file"]).is_file())
        self.assertTrue((self.root / second_payload["file"]).is_file())

    def test_status_without_delivery_reports_no_history(self) -> None:
        self._seed()
        result = self.cli("status", "--project", str(self.root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["delivery"]["has_delivery"])


if __name__ == "__main__":
    unittest.main()
