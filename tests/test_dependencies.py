import json
import tempfile
import unittest
from pathlib import Path

from my_slides.cli import init_project, slug, template_chapters
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
)
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
        mark_report_approved(self.base, units[0], project_root=self.root, when="2026-01-01T00:00:00+00:00")
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


if __name__ == "__main__":
    unittest.main()
