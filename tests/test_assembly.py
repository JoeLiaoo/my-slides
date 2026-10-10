import argparse
import json
import re
import tempfile
import unittest
from pathlib import Path

from my_slides.assembly import build_units_deck, compile_unit_page
from my_slides.commands.init import init_project
from my_slides.browser_runtime import browser_status
from my_slides.project import template_chapters
from my_slides.rendering import renderer_status
from my_slides.sources import mark_ingested, scan_sources
from my_slides.state import collect_units_status
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec, assemble_after_report_approvals
from my_slides.units import Unit, unit_paths, write_units_manifest
from my_slides.wiki import validate_wiki

TEST_APPROVER = {"approved_by": "Fixture Reviewer", "approved_account": "fixture"}


def _spec(unit_id: str, role: str) -> str:
    return (
        f"## Slide 1 — {unit_id}\n页面 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        "### 布局意图\nLayout.\n### 图标需求\n无\n"
    )


def _page(unit_id: str, role: str) -> str:
    return _pages(unit_id, role, [unit_id])


def _spec_pages(unit_id: str, role: str, titles: list[str]) -> str:
    parts = [f"单元 ID：{unit_id}", f"页面角色：{role}", ""]
    for number, title in enumerate(titles, start=1):
        parts.append(
            f"## Slide {number} — {title}\n"
            "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
            "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
            "### 布局意图\nLayout.\n### 图标需求\n无\n"
        )
    return "\n".join(parts)


def _pages(unit_id: str, role: str, titles: list[str]) -> str:
    return "\n".join(
        f'<section class="slide" data-page-role="{role}" data-unit-id="{unit_id}">'
        f"<h1>{title}</h1>"
        f'<script type="application/json" class="slide-notes">'
        f'{{"title":"{title}","script":"Hi","notes":[]}}</script></section>'
        for title in titles
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
            approve_unit_report(self.base, unit, when="t0", project_root=self.root, **TEST_APPROVER)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root, **TEST_APPROVER)
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

    def test_legacy_spec_without_reviewer_cannot_build(self):
        from my_slides.state import read_unit_state, write_unit_state

        self._seed()
        state = read_unit_state(self.base, "summary-01")
        state["spec"]["approved_by"] = None
        state["spec"]["approved_account"] = None
        write_unit_state(self.base, "summary-01", state)
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertIsNone(output)
        self.assertTrue(any("Spec 未批准" in error for error in errors), errors)
        self.assertFalse((self.base / "slides" / "index.html").exists())

    def test_unit_build_requires_valid_notes(self):
        self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        page = unit_paths(self.base, "summary-01").page
        valid = page.read_text(encoding="utf-8")
        page.write_text(re.sub(r'<script[^>]*class="slide-notes".*?</script>', "", valid), encoding="utf-8")
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertIsNone(output)
        self.assertTrue(any("slide-notes" in error for error in errors), errors)
        page.write_text(valid, encoding="utf-8")
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        self.assertTrue(output.is_file())

    def test_chart_data_must_match_approved_unit_spec(self):
        units = self._seed()
        chart = {"type": "bar", "categories": ["2024", "2025"], "values": [10, 14], "unit": "亿元"}
        spec = unit_paths(self.base, "summary-01").spec
        spec.write_text(_spec("summary-01", "content") + "\n```echarts-spec\n" + json.dumps(chart, ensure_ascii=False) + "\n```\n", encoding="utf-8")
        approve_unit_spec(self.base, units[1], when="t2", project_root=self.root, **TEST_APPROVER)
        chart["values"] = [10, 15]
        page = unit_paths(self.base, "summary-01").page
        page.write_text(
            _page("summary-01", "content").replace(
                '<script type="application/json" class="slide-notes">',
                '<script type="application/json" class="mls-echarts-spec">'
                + json.dumps(chart, ensure_ascii=False) + '</script>'
                '<script type="application/json" class="slide-notes">',
            ), encoding="utf-8",
        )
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertIsNone(output)
        self.assertTrue(any("完全一致" in error for error in errors), errors)

    def test_deck_keeps_active_word_in_body_text(self):
        self._seed()
        page = unit_paths(self.base, "summary-01").page
        page.write_text(_page("summary-01", "content").replace(
            'class="slide"', 'class="slide active"',
        ).replace("<h1>summary-01</h1>", "<h1>summary-01</h1><p>The market is active today</p>"), encoding="utf-8")
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        html = output.read_text(encoding="utf-8")
        self.assertIn("The market is active today", html)
        second = re.search(r'<section[^>]*data-slide="1"[^>]*>', html)
        self.assertIsNotNone(second)
        self.assertNotRegex(second.group(0), r'\bactive\b')

    @unittest.skipUnless(renderer_status()["ready"] and browser_status()["chromium_installed"],
                         "local renderer or Playwright Chromium is unavailable")
    def test_chart_icon_deck_is_offline_and_archives_rebuild(self):
        from my_slides.browser import check_deck

        units = self._seed()
        chart = {"type": "bar", "title": "Revenue", "categories": ["2024", "2025"],
                 "values": [10, 14], "unit": "亿元"}
        spec = unit_paths(self.base, "summary-01").spec
        spec.write_text(
            _spec("summary-01", "content").replace("### 图标需求\n无", "### 图标需求\narrow-right")
            + "\n```echarts-spec\n" + json.dumps(chart, ensure_ascii=False) + "\n```\n",
            encoding="utf-8",
        )
        approve_unit_spec(self.base, units[1], when="t2", project_root=self.root, **TEST_APPROVER)
        page = unit_paths(self.base, "summary-01").page
        page.write_text(
            _page("summary-01", "content").replace(
                '<script type="application/json" class="slide-notes">',
                '<script type="application/json" class="mls-echarts-spec">'
                + json.dumps(chart, ensure_ascii=False) + '</script>'
                '<script type="application/json" class="mls-lucide-spec">{"name":"arrow-right"}</script>'
                '<script type="application/json" class="slide-notes">',
            ), encoding="utf-8",
        )
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [], errors)
        first = output.read_bytes()
        self.assertIn("<svg", first.decode("utf-8"))
        self.assertNotIn("mls-echarts-spec", first.decode("utf-8"))
        self.assertIn("third-party-notices", first.decode("utf-8"))
        checked = check_deck(output, unit_ids=["cover", "summary-01"])
        self.assertTrue(checked["valid"], checked)
        self.assertEqual(checked["external_requests"], [])
        page.write_text(page.read_text(encoding="utf-8").replace("<h1>summary-01</h1>", "<h1>Revenue revised</h1>"), encoding="utf-8")
        output, errors, _ = build_units_deck(self.base, cfg, unit_ids=["summary-01"], write=True)
        self.assertEqual(errors, [], errors)
        self.assertNotEqual(output.read_bytes(), first)
        self.assertTrue(any((self.base / ".state" / "deliveries").glob("*.html")))

    def test_synthetic_six_chapter_unit_project_end_to_end(self):
        from my_slides.browser import structural_check_deck

        chapters = template_chapters()
        self.assertEqual(len(chapters), 6)
        source_dir = self.root / "sources"
        source_dir.mkdir()
        (source_dir / "metrics.md").write_text("# Metrics\n\nRevenue: 10, 14, 19.\n", encoding="utf-8")
        wiki = self.base / "wiki" / "company.md"
        wiki.write_text("# Company\n\n[Revenue source](../../sources/metrics.md).\n", encoding="utf-8")
        index = self.base / "wiki" / "index.md"
        index.write_text(index.read_text(encoding="utf-8").replace(
            "## 投资概要", "## 投资概要\n\n- [Company](company.md) — synthetic evidence",
        ), encoding="utf-8")
        cfg = {"project": "Synthetic", "chapters": chapters, "brand_color": "#A6192E"}
        self.assertEqual(validate_wiki(self.base, cfg), [])
        _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["sources"]})
        self.assertEqual(pending, ["sources/metrics.md"])
        self.assertEqual(removed, [])
        self.assertEqual(mark_ingested(self.base, pending), 1)
        units: list[Unit] = []
        for number, chapter in enumerate(chapters, 1):
            units.append(Unit(
                id=f"chapter-{number}",
                chapter=chapter,
                role="cover" if number == 1 else "content",
                title=chapter,
            ))
            units.append(Unit(
                id=f"chapter-{number}-detail",
                chapter=chapter,
                role="content",
                title=f"{chapter}补充",
            ))
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            page_titles = ["概览", "结构", "结论"] if unit.id == "chapter-2-detail" else ["概览"]
            paths.report.write_text(
                f"# {unit.title}\n\nSynthetic investment analysis using [company evidence](../../wiki/company.md).\n",
                encoding="utf-8",
            )
            paths.spec.write_text(_spec_pages(unit.id, unit.role, page_titles), encoding="utf-8")
            paths.page.write_text(_pages(unit.id, unit.role, page_titles), encoding="utf-8")
            approve_unit_report(self.base, unit, when="t0", project_root=self.root, **TEST_APPROVER)
        document, errors = assemble_after_report_approvals(self.base)
        self.assertEqual(errors, [], errors)
        self.assertEqual(document.count("company evidence"), 12)
        for unit in units:
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root, **TEST_APPROVER)
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [], errors)
        structural = structural_check_deck(output, expected_units=[unit.id for unit in units])
        self.assertTrue(structural["valid"], structural["errors"])
        detail = next(item for item in structural["sections"] if item["id"] == "chapter-2-detail")
        self.assertEqual(detail["pages"], 3)
        state = collect_units_status(self.base, chapters=chapters, project_root=self.root)
        self.assertEqual(len(state["units"]), 12)
        self.assertTrue(all(row["report_current"] and row["spec_current"] and row["html_current"]
                            for row in state["units"]))

    def test_assembled_deck_has_exactly_one_data_unit_id_per_unit(self):
        """Pages already carry data-unit-id; assemble must not inject a duplicate."""
        import re

        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        # compile_unit_page may also stamp data-unit-id; seed pages already have it.
        for unit in units:
            fragment, errors = compile_unit_page(
                self.base, unit, brand_color=cfg["brand_color"], write_preview=True
            )
            self.assertEqual(errors, [], errors)
            self.assertEqual(len(re.findall(r'data-unit-id=', fragment)), 1, fragment)
        output, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [], errors)
        html = output.read_text(encoding="utf-8")
        found = re.findall(r'data-unit-id="([^"]+)"', html)
        self.assertEqual(found, [unit.id for unit in units], found)
        for unit_id in found:
            self.assertEqual(found.count(unit_id), 1, found)

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

    def test_incremental_build_does_not_reuse_html_from_previous_spec(self):
        import json

        from my_slides.assembly import _cache_path
        from my_slides.state import read_unit_state, refresh_unit_currency

        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        _, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        state = read_unit_state(self.base, "summary-01")
        cache = _cache_path(self.base, state["html"]["cache_key"])
        payload = json.loads(cache.read_text(encoding="utf-8"))
        payload["html"] = payload["html"].replace("<h1>summary-01</h1>", "<h1>STALE</h1>")
        cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        spec_path = unit_paths(self.base, "summary-01").spec
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace("Conclusion.", "Conclusion revised."),
            encoding="utf-8",
        )
        approve_unit_spec(self.base, units[1], when="t2", project_root=self.root, **TEST_APPROVER)
        output, errors, plan = build_units_deck(self.base, cfg, unit_ids=["cover"], write=True)
        self.assertEqual(errors, [], errors)
        self.assertNotIn("summary-01", plan["reused"])
        self.assertIn("summary-01", plan["rebuild"])
        self.assertNotIn("STALE", output.read_text(encoding="utf-8"))
        refreshed = refresh_unit_currency(self.base, units[1], project_root=self.root)
        self.assertEqual(refreshed["html"].get("spec_sha256"), refreshed["spec"].get("approved_sha256"))

    def test_recorded_browser_check_stays_current_after_refresh(self):
        from my_slides.browser import record_unit_check_results
        from my_slides.state import refresh_unit_currency

        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        deck, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        record_unit_check_results(
            self.base, [unit.id for unit in units], passed=True, deck_path=deck
        )
        for unit in units:
            state = refresh_unit_currency(self.base, unit, project_root=self.root)
            self.assertTrue(state["check"]["current"], state)

    def test_browser_check_binds_to_measured_build_not_edited_source(self):
        """Editing page source then checking the old deck must not keep check current after rebuild."""
        from my_slides.browser import record_unit_check_results
        from my_slides.state import read_unit_state, refresh_unit_currency

        units = self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        deck, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        page = unit_paths(self.base, "summary-01").page
        page.write_text(
            page.read_text(encoding="utf-8").replace("<h1>summary-01</h1>", "<h1>WIDER</h1>"),
            encoding="utf-8",
        )
        # Measures old index.html; must bind to built version + that deck, not the new source.
        record_unit_check_results(self.base, ["summary-01"], passed=True, deck_path=deck)
        _, errors, _ = build_units_deck(self.base, cfg, unit_ids=["summary-01"], write=True)
        self.assertEqual(errors, [])
        state = refresh_unit_currency(self.base, units[1], project_root=self.root)
        self.assertFalse(state["check"]["current"], read_unit_state(self.base, "summary-01"))

    def test_brand_color_change_does_not_reuse_stale_cache(self):
        """Incremental assemble after brand_color change must not reuse old-key cache entries."""
        from my_slides.assembly import compute_unit_cache_key
        from my_slides.state import read_unit_state

        self._seed()
        cfg = {"project": "Demo", "chapters": ["投资概要"], "brand_color": "#A6192E"}
        _, errors, _ = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [])
        old_key = read_unit_state(self.base, "summary-01")["html"]["cache_key"]
        cfg_new = {**cfg, "brand_color": "#003366"}
        new_key, key_errors, _ = compute_unit_cache_key(
            self.base,
            Unit(id="summary-01", chapter="投资概要", role="content"),
            brand_color=cfg_new["brand_color"],
        )
        self.assertEqual(key_errors, [])
        self.assertNotEqual(old_key, new_key)
        # Rebuild only cover under new brand; summary must not reuse the old brand cache key.
        output, errors, plan = build_units_deck(self.base, cfg_new, unit_ids=["cover"], write=True)
        self.assertEqual(errors, [], errors)
        self.assertNotIn("summary-01", plan["reused"])
        self.assertIn("summary-01", plan["rebuild"])
        self.assertIsNotNone(output)
        self.assertEqual(
            read_unit_state(self.base, "summary-01")["html"]["cache_key"],
            new_key,
        )


if __name__ == "__main__":
    unittest.main()
