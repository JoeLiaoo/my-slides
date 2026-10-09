import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.state import read_unit_state
from my_slides.unit_workflow import (
    approve_unit_report,
    approve_unit_spec,
    validate_unit_report,
    validate_unit_spec,
)
from my_slides.units import Unit, assemble_report, detect_format_version, unit_paths, write_units_manifest


def _spec_body(unit_id: str, role: str) -> str:
    return (
        f"## Slide 1 — {unit_id}\n页面 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\nLayout.\n### 图标需求\n无\n"
    )


class UnitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"

    def tearDown(self):
        self.temp.cleanup()

    def init_v2(self):
        init_project(
            argparse.Namespace(
                project=str(self.root),
                source_dir=None,
                force=False,
                json=False,
            )
        )
        self.assertEqual(detect_format_version(self.base), "v2")
        self.assertTrue((self.base / "reports" / "units").is_dir())

    def test_init_v2_creates_units_and_directories(self):
        self.init_v2()
        self.assertTrue((self.base / "units.json").is_file())
        self.assertTrue((self.base / "slides" / "pages").is_dir())

    def test_unit_report_spec_approve_and_assemble(self):
        self.init_v2()
        units = [
            Unit(id="cover", chapter="投资概要", role="cover"),
            Unit(id="summary-01", chapter="投资概要", role="content"),
        ]
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            paths.report.parent.mkdir(parents=True, exist_ok=True)
            paths.spec.parent.mkdir(parents=True, exist_ok=True)
            paths.page.parent.mkdir(parents=True, exist_ok=True)
            paths.report.write_text(
                f"# {unit.id}\n\n" + "Detailed investment analysis text. " * 3 + "\n",
                encoding="utf-8",
            )
            paths.spec.write_text(_spec_body(unit.id, unit.role), encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" data-unit-id="{unit.id}" data-page-role="{unit.role}"></section>',
                encoding="utf-8",
            )
        self.assertEqual(validate_unit_report(self.base, units[1]), [])
        self.assertEqual(validate_unit_spec(self.base, units[1]), [])
        approve_unit_report(self.base, units[0], when="t0", project_root=self.root)
        approve_unit_report(self.base, units[1], when="t0", project_root=self.root)
        document, errors = assemble_report(self.base, units, write=True)
        self.assertEqual(errors, [])
        self.assertIn("summary-01", document)
        approve_unit_spec(self.base, units[1], when="t1", project_root=self.root)
        state = read_unit_state(self.base, "summary-01")
        self.assertTrue(state["report"]["current"])
        self.assertTrue(state["spec"]["current"])
        # Re-approving report must not auto-revive Spec.
        paths = unit_paths(self.base, "summary-01")
        paths.report.write_text(paths.report.read_text(encoding="utf-8") + "\nExtra.\n", encoding="utf-8")
        approve_unit_report(self.base, units[1], when="t2", project_root=self.root)
        state = read_unit_state(self.base, "summary-01")
        self.assertTrue(state["report"]["current"])
        self.assertFalse(state["spec"]["current"])

    def test_cli_unit_approve_json(self):
        self.init_v2()
        units = [Unit(id="cover", chapter="投资概要", role="cover")]
        write_units_manifest(self.base, units)
        paths = unit_paths(self.base, "cover")
        paths.report.parent.mkdir(parents=True, exist_ok=True)
        paths.spec.parent.mkdir(parents=True, exist_ok=True)
        paths.page.parent.mkdir(parents=True, exist_ok=True)
        paths.report.write_text("# cover\n\n" + "Cover narrative with enough length. " * 3, encoding="utf-8")
        paths.spec.write_text(_spec_body("cover", "cover"), encoding="utf-8")
        paths.page.write_text('<section class="slide" data-unit-id="cover" data-page-role="cover"></section>', encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "my_slides.cli",
                "approve",
                "report",
                "--unit",
                "cover",
                "--project",
                str(self.root),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["requested"])
        self.assertFalse(payload["approved"])
        self.assertEqual(payload["units"][0]["id"], "cover")
        self.assertTrue(read_unit_state(self.base, "cover")["report"]["pending_current"])


if __name__ == "__main__":
    unittest.main()
