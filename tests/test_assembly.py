import argparse
import tempfile
import unittest
from pathlib import Path

from my_slides.assembly import build_units_deck, compile_unit_page
from my_slides.cli import init_project
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec
from my_slides.units import Unit, unit_paths, write_units_manifest


def _spec(unit_id: str, role: str) -> str:
    return (
        f"## Slide 1 — {unit_id}\n页面 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\nLayout.\n### 图标需求\n无\n"
    )


def _page(unit_id: str, role: str) -> str:
    return (
        f'<section class="slide" id="{unit_id}" data-page-role="{role}" data-unit-id="{unit_id}">'
        f"<h1>{unit_id}</h1>"
        f'<script type="application/json" class="slide-notes">'
        f'{{"title":"{unit_id}","script":"Hi","notes":[]}}</script></section>'
    )


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(
            argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False)
        )

    def tearDown(self):
        self.temp.cleanup()

    def _seed(self):
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
            paths.report.write_text(f"# {unit.id}\n\n" + "Enough report text for approval. " * 3, encoding="utf-8")
            paths.spec.write_text(_spec(unit.id, unit.role), encoding="utf-8")
            paths.page.write_text(_page(unit.id, unit.role), encoding="utf-8")
            approve_unit_report(self.base, unit, when="t0", project_root=self.root)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root)
        return units

    def test_unit_build_writes_preview_and_index(self):
        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        output, errors, plan = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [], errors)
        self.assertIsNotNone(output)
        self.assertTrue(output.is_file())
        self.assertTrue(unit_paths(self.base, "cover").preview.is_file())
        html = output.read_text(encoding="utf-8")
        self.assertIn('data-unit-id="cover"', html)
        self.assertIn('data-unit-id="summary-01"', html)
        self.assertIn("cover", plan["rebuild"] + plan["reused"])

    def test_partial_unit_keeps_prior_index_when_others_blocked(self):
        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        build_units_deck(self.base, cfg, all_units=True, write=True)
        prior = (self.base / "slides" / "index.html").read_text(encoding="utf-8")
        # Break summary page so only cover can rebuild.
        unit_paths(self.base, "summary-01").page.write_text("<div>broken</div>", encoding="utf-8")
        output, errors, plan = build_units_deck(self.base, cfg, unit_ids=["summary-01"], write=True)
        self.assertIsNone(output)
        self.assertTrue(errors)
        self.assertEqual((self.base / "slides" / "index.html").read_text(encoding="utf-8"), prior)

    def test_incremental_unit_build_matches_full_rebuild(self):
        """Same inputs: --unit incremental assemble equals --all (content parity)."""
        self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        full, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        full_html = full.read_text(encoding="utf-8")
        # Touch one page and rebuild only that unit, then rebuild all again.
        page = unit_paths(self.base, "summary-01").page
        page.write_text(page.read_text(encoding="utf-8").replace("<h1>summary-01</h1>", "<h1>summary-01 revised</h1>"), encoding="utf-8")
        inc, errors, plan = build_units_deck(self.base, cfg, unit_ids=["summary-01"], write=True)
        self.assertEqual(errors, [])
        self.assertIn("summary-01", plan["rebuild"])
        after_inc = inc.read_text(encoding="utf-8")
        again, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        after_all = again.read_text(encoding="utf-8")
        self.assertEqual(after_inc, after_all)
        self.assertIn("summary-01 revised", after_all)
        self.assertNotEqual(full_html, after_all)


if __name__ == "__main__":
    unittest.main()
