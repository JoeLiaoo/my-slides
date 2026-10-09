import json
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.project import template_chapters
from my_slides.units import slug
from my_slides.dependencies import (
    build_unit_dependency_graph,
    content_fingerprint,
    detect_unit_cycles,
    fingerprint_file,
    reliable_relpath,
    units_affected_by_file,
    walk_local_dependencies,
)
from my_slides.state import (
    collect_units_status,
    invalidate_for_changed_file,
    mark_report_approved,
    read_unit_state,
    refresh_unit_currency,
)
from my_slides.unit_workflow import approve_unit_spec
from my_slides.units import Unit, UnitsError, unit_paths, write_units_manifest
import argparse


class DependencyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.chapters = template_chapters()
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        units = self.base / "units.json"
        if units.exists():
            units.unlink()
        (self.base / "slides" / "chapters").mkdir(parents=True, exist_ok=True)


    def tearDown(self):
        self.temp.cleanup()

    def _write_units(self, units: list[Unit], reports: dict[str, str] | None = None):
        write_units_manifest(self.base, units)
        for unit in units:
            paths = unit_paths(self.base, unit.id)
            paths.report.parent.mkdir(parents=True, exist_ok=True)
            paths.spec.parent.mkdir(parents=True, exist_ok=True)
            paths.page.parent.mkdir(parents=True, exist_ok=True)
            paths.report.write_text(
                (reports or {}).get(unit.id, f"# {unit.id}\n\nBody for {unit.chapter}.\n"),
                encoding="utf-8",
            )
            paths.spec.write_text(f"## Slide 1 — {unit.id}\n页面 ID：{unit.id}\n页面角色：{unit.role}\n", encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" id="{unit.id}" data-page-role="{unit.role}"></section>',
                encoding="utf-8",
            )

    def test_fingerprint_ignores_mtime_and_normalizes_newlines(self):
        path = self.base / "wiki" / "sample.md"
        path.write_text("hello\r\nworld\n", encoding="utf-8")
        first = fingerprint_file(path)
        path.write_text("hello\nworld\n", encoding="utf-8")
        second = fingerprint_file(path)
        self.assertEqual(first, second)
        self.assertEqual(content_fingerprint("a\r\nb"), content_fingerprint("a\nb"))

    def test_wiki_change_only_affects_linked_units(self):
        wiki_w = self.base / "wiki" / "linked.md"
        wiki_other = self.base / "wiki" / "other.md"
        wiki_w.write_text("# Linked\n", encoding="utf-8")
        wiki_other.write_text("# Other\n", encoding="utf-8")
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="uses-w", chapter=self.chapters[0], role="content"),
            Unit(id="no-link", chapter=self.chapters[1], role="content"),
        ]
        self._write_units(
            units,
            reports={
                "cover": "# Cover\n\nOpening.\n",
                "uses-w": "# A\n\nSee [W](../../wiki/linked.md).\n",
                "no-link": "# B\n\nIndependent analysis without that wiki.\n",
            },
        )
        impact = units_affected_by_file(self.base, units, wiki_w, project_root=self.root)
        self.assertEqual(impact["affected_units"], ["uses-w"])
        wiki_w.write_text("# Linked\n\nUpdated.\n", encoding="utf-8")
        result = invalidate_for_changed_file(self.base, wiki_w, chapters=self.chapters, project_root=self.root)
        self.assertEqual(result["affected_units"], ["uses-w"])
        status = collect_units_status(self.base, chapters=self.chapters, project_root=self.root)
        by_id = {row["id"]: row for row in status["units"]}
        self.assertFalse(by_id["uses-w"]["report_current"])
        # Unrelated unit stays without forced stale reasons from this wiki.
        self.assertNotIn("uses-w", by_id["no-link"]["reasons"])

    def test_unit_dependency_cycle_reports_path(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="alpha", chapter=self.chapters[0], role="content"),
            Unit(id="beta", chapter=self.chapters[0], role="content"),
        ]
        self._write_units(units)
        dep_dir = unit_paths(self.base, "alpha").report.parent
        (dep_dir / "alpha.depends-on.json").write_text(json.dumps(["beta"]), encoding="utf-8")
        (dep_dir / "beta.depends-on.json").write_text(json.dumps(["alpha"]), encoding="utf-8")
        graph = build_unit_dependency_graph(self.base, units)
        errors = detect_unit_cycles(graph)
        self.assertTrue(errors)
        self.assertTrue(any("alpha" in error and "beta" in error for error in errors), errors)
        with self.assertRaises(UnitsError) as ctx:
            collect_units_status(self.base, chapters=self.chapters, project_root=self.root)
        self.assertIn("成环", str(ctx.exception))

    def test_percent_encoded_and_spaced_paths(self):
        notes = self.base / "wiki" / "my notes.md"
        notes.write_text("# Notes\n", encoding="utf-8")
        units = [Unit(id="cover", chapter=self.chapters[0], role="cover")]
        self._write_units(
            units,
            reports={"cover": "# Cover\n\n[n](../../wiki/my%20notes.md)\n"},
        )
        deps, warnings = walk_local_dependencies(
            unit_paths(self.base, "cover").report,
            root=self.root,
        )
        self.assertEqual(warnings, [])
        self.assertEqual([p.resolve() for p in deps], [notes.resolve()])

    def test_reliable_relpath_handles_sibling_trees(self):
        left = self.root / "a" / "b" / "c.txt"
        right = self.root / "a" / "x"
        left.parent.mkdir(parents=True)
        right.mkdir(parents=True)
        left.write_text("x", encoding="utf-8")
        rel = reliable_relpath(left, right)
        self.assertEqual(rel.as_posix(), "../b/c.txt")

    def test_status_unit_json_skeleton_fields(self):
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="summary-01", chapter=self.chapters[0], role="content"),
        ]
        self._write_units(units)
        mark_report_approved(self.base, units[0], project_root=self.root, when="2026-01-01T00:00:00+00:00", approved_by="Fixture Reviewer", approved_account="fixture")
        status = collect_units_status(
            self.base,
            selected=["cover"],
            chapters=self.chapters,
            project_root=self.root,
        )
        for key in ("selected_units", "affected_units", "reused_units", "blocked_units", "reasons"):
            self.assertIn(key, status)
        self.assertEqual(status["selected_units"], ["cover"])
        state = read_unit_state(self.base, "cover")
        self.assertTrue(state["report"]["current"])

    def test_approved_report_stale_after_linked_wiki_changes(self):
        wiki = self.base / "wiki" / "linked.md"
        wiki.write_text("# Linked\n", encoding="utf-8")
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="uses-w", chapter=self.chapters[0], role="content"),
        ]
        self._write_units(
            units,
            reports={
                "cover": "# Cover\n\nOpening statement for the deck.\n",
                "uses-w": "# A\n\nSee [W](../../wiki/linked.md) for the cited evidence.\n",
            },
        )
        mark_report_approved(self.base, units[1], project_root=self.root, when="t0", approved_by="Fixture Reviewer", approved_account="fixture")
        self.assertTrue(read_unit_state(self.base, "uses-w")["report"]["current"])
        wiki.write_text("# Linked\n\nUpdated fact.\n", encoding="utf-8")
        status = collect_units_status(self.base, chapters=self.chapters, project_root=self.root)
        by_id = {row["id"]: row for row in status["units"]}
        self.assertFalse(by_id["uses-w"]["report_current"])

    def test_upstream_dependency_change_stales_downstream_approval(self):
        wiki = self.base / "wiki" / "linked.md"
        wiki.write_text("# Linked\n", encoding="utf-8")
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="upstream", chapter=self.chapters[0], role="content"),
            Unit(id="downstream", chapter=self.chapters[1], role="content"),
        ]
        self._write_units(
            units,
            reports={
                "cover": "# Cover\n\nOpening statement for the deck.\n",
                "upstream": "# Up\n\nSee [W](../../wiki/linked.md) for the cited evidence.\n",
                "downstream": "# Down\n\nUses the upstream unit without linking that wiki.\n",
            },
        )
        sidecar = unit_paths(self.base, "downstream").report.parent / "downstream.depends-on.json"
        sidecar.write_text(json.dumps(["upstream"]), encoding="utf-8")
        for unit in units:
            if unit.id == "cover":
                continue
            mark_report_approved(self.base, unit, project_root=self.root, when="t0", approved_by="Fixture Reviewer", approved_account="fixture")
        wiki.write_text("# Linked\n\nUpdated fact.\n", encoding="utf-8")
        status = collect_units_status(self.base, chapters=self.chapters, project_root=self.root)
        by_id = {row["id"]: row for row in status["units"]}
        self.assertFalse(by_id["upstream"]["report_current"])
        self.assertFalse(by_id["downstream"]["report_current"])

    def test_binary_image_dependency_can_be_fingerprinted(self):
        import hashlib

        raw = b"\x89PNG\r\n\x1a\n\xff\xfe"
        self.assertEqual(content_fingerprint(raw), hashlib.sha256(raw).hexdigest())
        image = self.base / "wiki" / "chart.png"
        image.write_bytes(raw)
        units = [Unit(id="cover", chapter=self.chapters[0], role="cover")]
        self._write_units(
            units,
            reports={"cover": "# Cover\n\nChart ![c](../../wiki/chart.png) supports the point.\n"},
        )
        mark_report_approved(self.base, units[0], project_root=self.root, when="t0", approved_by="Fixture Reviewer", approved_account="fixture")
        self.assertTrue(read_unit_state(self.base, "cover")["report"]["current"])

    def test_reapprove_unchanged_report_after_deps_change_keeps_spec_stale(self):
        """Spec/HTML must stay stale when only dependencies changed and report body is re-approved."""
        wiki = self.base / "wiki" / "linked.md"
        wiki.write_text("# Linked\n", encoding="utf-8")
        units = [
            Unit(id="cover", chapter=self.chapters[0], role="cover"),
            Unit(id="uses-w", chapter=self.chapters[0], role="content"),
        ]
        self._write_units(
            units,
            reports={
                "cover": "# Cover\n\nOpening statement for the deck.\n",
                "uses-w": "# A\n\nSee [W](../../wiki/linked.md) for the cited evidence.\n",
            },
        )
        paths = unit_paths(self.base, "uses-w")
        paths.spec.write_text(
            "## Slide 1 — uses-w\n页面 ID：uses-w\n页面角色：content\n"
            "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
            "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
            "### 布局意图\nLayout.\n### 图标需求\n无\n",
            encoding="utf-8",
        )
        paths.page.write_text(
            '<section class="slide" data-unit-id="uses-w" data-page-role="content">'
            "<h1>uses-w</h1>"
            '<script type="application/json" class="slide-notes">'
            '{"title":"uses-w","script":"Hi","notes":[]}</script></section>',
            encoding="utf-8",
        )
        mark_report_approved(self.base, units[1], project_root=self.root, when="t0", approved_by="Fixture Reviewer", approved_account="fixture")
        approve_unit_spec(self.base, units[1], when="t1", project_root=self.root, approved_by="Fixture Reviewer", approved_account="fixture")
        # Simulate a prior HTML build bound to that Spec.
        state = read_unit_state(self.base, "uses-w")
        state["html"] = {
            "content_sha256": fingerprint_file(paths.page),
            "spec_sha256": state["spec"]["approved_sha256"],
            "build_sha256": fingerprint_file(paths.page),
            "cache_key": "test-key",
            "current": True,
        }
        from my_slides.state import write_unit_state

        write_unit_state(self.base, "uses-w", state)
        wiki.write_text("# Linked\n\nUpdated fact.\n", encoding="utf-8")
        refreshed = refresh_unit_currency(self.base, units[1], project_root=self.root)
        self.assertFalse(refreshed["report"]["current"])
        self.assertFalse(refreshed["spec"]["current"])
        # Re-approve same report body against new deps — must not revive Spec/HTML.
        mark_report_approved(self.base, units[1], project_root=self.root, when="t2", approved_by="Fixture Reviewer", approved_account="fixture")
        again = refresh_unit_currency(self.base, units[1], project_root=self.root)
        self.assertTrue(again["report"]["current"])
        self.assertFalse(again["spec"]["current"], again)
        self.assertFalse(again["html"]["current"], again)


if __name__ == "__main__":
    unittest.main()
