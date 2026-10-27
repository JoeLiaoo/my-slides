from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides.commands import export as export_command
from my_slides.commands.init import init_project
from my_slides.delivery import (
    DELIVERY_FILENAME_RE,
    export_delivery,
    list_deliveries,
    units_changed_since,
)
from my_slides.design_deck import deck_dir, sync_deck
from my_slides.project import read_config, template_chapters
from my_slides.unit_workflow import approve_unit_report
from my_slides.units import Unit, unit_paths, write_units_manifest


def fake_engine_export(command: list[str], projects_root: Path, **_: object) -> tuple[int, dict]:
    """Stand-in for the Design agent CLI: write the --out file like a real export."""
    out = Path(command[command.index("--out") + 1])
    out.write_text("<!doctype html><html><body>deck</body></html>", encoding="utf-8")
    return 0, {"ok": True, "code": "exported", "path": str(out), "sourceVersion": "v-test"}


class ExportDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        offline = patch("my_slides.design_deck.host_reachable", return_value=False)
        engine = patch("my_slides.delivery.run_agent", side_effect=fake_engine_export)
        offline.start()
        self.engine = engine.start()
        self.addCleanup(offline.stop)
        self.addCleanup(engine.stop)

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
            paths.report.write_text(
                f"# {unit.id}\n\nDetailed, evidence-backed analysis for {unit.id}. " * 3,
                encoding="utf-8",
            )
        return units

    def _approve(self, units: list[Unit]) -> None:
        for unit in units:
            approve_unit_report(
                self.base, unit, when="2024-01-01T00:00:00",
                approved_by="Reviewer", approved_account="reviewer", project_root=self.root,
            )

    def _ready(self) -> list[Unit]:
        units = self._seed()
        self._approve(units)
        sync_deck(self.base, read_config(self.base / "project.yaml"), units)
        return units

    def test_export_records_named_file_and_page_hashes(self) -> None:
        self._ready()
        cfg = read_config(self.base / "project.yaml")
        record = export_delivery(self.base, cfg, project_root=self.root)
        today = datetime.date.today().strftime("%Y-%m-%d")
        match = DELIVERY_FILENAME_RE.fullmatch(record["file"])
        self.assertIsNotNone(match, record["file"])
        self.assertEqual(match.group("date"), today)
        self.assertEqual(match.group("sequence"), "1")
        self.assertTrue((self.root / record["file"]).is_file())
        command = self.engine.call_args.args[0]
        self.assertEqual(command[:4], ["export", "deck", "--format", "html"])

        deliveries = list_deliveries(self.base)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["presentation"], "design")
        self.assertEqual({item["id"] for item in deliveries[0]["units"]}, {"cover", "alpha"})
        alpha = next(item for item in deliveries[0]["units"] if item["id"] == "alpha")
        self.assertEqual(list(alpha["pages"]), ["alpha"])
        self.assertTrue(deliveries[0]["deck_fingerprint"])

    def test_export_increments_sequence_within_same_day(self) -> None:
        self._ready()
        cfg = read_config(self.base / "project.yaml")
        first = export_delivery(self.base, cfg, project_root=self.root)
        second = export_delivery(self.base, cfg, project_root=self.root)
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        self.assertNotEqual(first["file"], second["file"])

    def test_export_refuses_unapproved_report_or_unit_without_page(self) -> None:
        units = self._ready()
        cfg = read_config(self.base / "project.yaml")
        report = unit_paths(self.base, "alpha").report
        report.write_text(report.read_text(encoding="utf-8") + "\n未审批的修改。\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "报告未获得当前有效批准：alpha"):
            export_delivery(self.base, cfg, project_root=self.root)
        self._approve(units)
        (deck_dir(self.base) / "slides" / "alpha.html").unlink()
        with self.assertRaisesRegex(ValueError, "alpha 还没有页面"):
            export_delivery(self.base, cfg, project_root=self.root)
        self.engine.assert_not_called()

    def test_export_refuses_when_deck_missing(self) -> None:
        units = self._seed()
        self._approve(units)
        cfg = read_config(self.base / "project.yaml")
        with self.assertRaisesRegex(ValueError, "slides build --all"):
            export_delivery(self.base, cfg, project_root=self.root)

    def test_export_failure_explains_host_requirement(self) -> None:
        self._ready()
        self.engine.side_effect = None
        self.engine.return_value = (2, {"ok": False, "code": "host_unavailable", "message": "fetch failed"})
        cfg = read_config(self.base / "project.yaml")
        with self.assertRaisesRegex(ValueError, "导出需要宿主在运行"):
            export_delivery(self.base, cfg, project_root=self.root)
        self.assertEqual(list_deliveries(self.base), [])

    def test_export_command_honors_output_dir(self) -> None:
        self._ready()
        target = self.root / "exports"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = export_command.run(argparse.Namespace(project=str(self.root), output=str(target), json=True))
        self.assertEqual(code, 0)
        self.assertTrue((target / json.loads(out.getvalue())["file"]).is_file())

    def test_status_shows_report_and_page_changes_since_delivery(self) -> None:
        units = self._ready()
        cfg = read_config(self.base / "project.yaml")
        export_delivery(self.base, cfg, project_root=self.root)
        report = unit_paths(self.base, "alpha").report
        report.write_text(report.read_text(encoding="utf-8") + "\n追加一句话。\n", encoding="utf-8")
        self._approve(units)
        page = deck_dir(self.base) / "slides" / "cover.html"
        page.write_text(page.read_text(encoding="utf-8").replace("[待写：封面副标题]", "副标题"), encoding="utf-8")

        result = self.cli("status", "--project", str(self.root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["delivery"]["has_delivery"])
        self.assertTrue(payload["delivery"]["deck_changed"])
        changed = {item["unit"]: item["reason"] for item in payload["delivery"]["changed_since"]}
        self.assertIn("报告正文", changed["alpha"])
        self.assertIn("Design 页面", changed["cover"])

    def test_units_changed_since_lists_missing_units(self) -> None:
        units = self._ready()
        cfg = read_config(self.base / "project.yaml")
        export_delivery(self.base, cfg, project_root=self.root)
        write_units_manifest(self.base, [unit for unit in units if unit.id == "cover"])
        delta = units_changed_since(self.base, self.root)
        self.assertEqual(delta["missing_units"], ["alpha"])
        self.assertEqual(delta["unchanged_units"], ["cover"])

    def test_status_without_delivery_reports_no_history(self) -> None:
        self._seed()
        result = self.cli("status", "--project", str(self.root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["delivery"]["has_delivery"])
        self.assertFalse(payload["slides"]["deck_exists"])


if __name__ == "__main__":
    unittest.main()
