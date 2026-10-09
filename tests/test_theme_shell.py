import argparse
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from my_slides.assembly import build_units_deck
from my_slides.cli import init_project
from my_slides.state import refresh_unit_currency
from my_slides.theme import THEME_NAME, shell_css, verify_assets
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec, prepare_unit_handoff
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
        f'<section class="slide" data-page-role="{role}" data-unit-id="{unit_id}">'
        f"<h1>{unit_id}</h1>"
        f'<script type="application/json" class="slide-notes">'
        f'{{"title":"{unit_id}","script":"Hi","notes":[]}}</script></section>'
    )


class ThemeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.units = [
            Unit(id="cover", chapter="投资概要", role="cover"),
            Unit(id="summary-01", chapter="投资概要", role="content"),
        ]
        write_units_manifest(self.base, self.units)
        for unit in self.units:
            paths = unit_paths(self.base, unit.id)
            paths.report.write_text(f"# {unit.id}\n\n" + "Enough report text for approval. " * 3, encoding="utf-8")
            paths.spec.write_text(_spec(unit.id, unit.role), encoding="utf-8")
            paths.page.write_text(_page(unit.id, unit.role), encoding="utf-8")
            approve_unit_report(self.base, unit, when="t0", project_root=self.root)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root)
        self.cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}

    def tearDown(self):
        self.temp.cleanup()

    def test_packaged_assets_match_manifest(self):
        self.assertEqual(verify_assets(), [])
        css = shell_css("#A6192E")
        self.assertIn("100dvh", css)
        self.assertIn("--brand: #A6192E", css)
        self.assertNotIn("fonts.googleapis", css)
        self.assertNotIn("@import", css)
        self.assertIn("PingFang SC", css)

    def test_preview_and_deck_share_shell(self):
        output, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        deck = output.read_text(encoding="utf-8")
        preview = unit_paths(self.base, "cover").preview.read_text(encoding="utf-8")
        page = unit_paths(self.base, "cover").page.read_text(encoding="utf-8")
        shared = shell_css(self.cfg["brand_color"])
        self.assertIn(shared, deck)
        self.assertIn(shared, preview)
        self.assertIn(f'my-slides-theme" content="{THEME_NAME}"', preview)
        self.assertIn('class="slide active"', preview)
        self.assertEqual(deck.count('id="controls"'), 1)
        self.assertNotIn("fitSlides", deck)
        self.assertNotIn("1920px", deck)
        self.assertNotIn("function goTo", page)
        self.assertNotIn('id="controls"', page)
        self.assertNotIn("fonts.googleapis", preview)
        self.assertNotIn("fonts.googleapis", deck)

    def test_theme_change_expires_html_not_approvals_and_rebuilds_match(self):
        from my_slides.browser import record_unit_check_results
        from my_slides.theme import theme_cache_fields

        deck, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        record_unit_check_results(self.base, [unit.id for unit in self.units], passed=True, deck_path=deck)
        self.assertTrue(refresh_unit_currency(self.base, self.units[1], project_root=self.root)["check"]["current"])

        def bumped_fields():
            data = dict(theme_cache_fields())
            data["shell_version"] = "bumped"
            return data

        with (
            patch("my_slides.assembly.theme_cache_fields", bumped_fields),
            patch("my_slides.assembly.shell_fingerprint", lambda: "bumped-shell"),
            patch("my_slides.theme.shell_fingerprint", lambda: "bumped-shell"),
        ):
            state = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
            self.assertTrue(state["report"]["current"])
            self.assertTrue(state["spec"]["current"])
            self.assertFalse(state["html"]["current"], state["reasons"])
            self.assertFalse(state["check"]["current"])
            incremental, errors, plan = build_units_deck(self.base, self.cfg, unit_ids=["cover"], write=True)
            self.assertEqual(errors, [])
            self.assertNotIn("summary-01", plan["reused"])
            full, errors, _ = build_units_deck(self.base, self.cfg, all_units=True, write=True)
            self.assertEqual(errors, [])
            self.assertEqual(incremental.read_text(encoding="utf-8"), full.read_text(encoding="utf-8"))

    def test_prepare_slides_handoff_lists_static_components(self):
        output = prepare_unit_handoff(self.base, self.root, self.units, "slides", stamp="t")
        text = output.read_text(encoding="utf-8")
        self.assertIn("stat-card", text)
        self.assertIn("vs-container", text)
        self.assertIn("table-wrap", text)
        self.assertIn("chart-container", text)
        self.assertIn("slides/previews/", text)
        self.assertNotIn("onclick", text)

    def test_wheel_contains_theme_assets(self):
        uv = shutil.which("uv")
        if not uv:
            self.skipTest("需要 uv 才能打 wheel")
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [uv, "build", "--wheel", "-o", tmp],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            wheels = list(Path(tmp).glob("*.whl"))
            self.assertEqual(len(wheels), 1, wheels)
            with zipfile.ZipFile(wheels[0]) as archive:
                names = archive.namelist()
        for suffix in (
            "slides_theme/upstream/viewport-base.css",
            "slides_theme/upstream/components.css",
            "slides_theme/upstream/editorial-light.css",
            "slides_theme/upstream/LICENSE",
            "slides_theme/adapt.css",
            "slides_theme/manifest.json",
            "slides_theme/component-examples.md",
        ):
            self.assertTrue(any(name.endswith(suffix) for name in names), suffix)


if __name__ == "__main__":
    unittest.main()
