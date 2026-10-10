import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides import __version__, format_version
from my_slides.agent_workflow import install_agent_workflow
from my_slides.commands.init import init_project
from my_slides.commands.prepare import prepare
from my_slides.project import find_slug_collisions, project_root, read_config, template_chapters
from my_slides.rendering import render_assets, renderer_status, validate_chart_spec
from my_slides.slide_fragments import SlideFragmentParser, extract_approved_icons, validate_scoped_css
from my_slides.sources import mark_ingested, scan_sources
from my_slides.wiki import sync_wiki_index, validate_wiki


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        import tomllib

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        self.assertEqual(__version__, data["project"]["version"])

    def test_cli_version_flags(self):
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        for flag in ("--version", "-V"):
            with self.subTest(flag=flag):
                result = subprocess.run(
                    [sys.executable, "-m", "my_slides.cli", flag],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=env,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), format_version())


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.cfg = {"project": "Demo", "chapters": template_chapters()}

    def tearDown(self):
        self.temp.cleanup()

    def init(self):
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def remove_units_manifest(self):
        """Remove units.json to exercise the unsupported-project diagnostic."""
        (self.base / "units.json").unlink()


    def test_default_wiki_index_matches_report_chapters(self):
        self.init()
        self.assertEqual(validate_wiki(self.base, self.cfg), [])
        index = self.base / "wiki" / "index.md"
        index.write_text("# Wiki Index\n\n## 其他\n", encoding="utf-8")
        self.assertTrue(any("缺少报告章节分组" in error for error in validate_wiki(self.base, self.cfg)))

    def test_agent_skill_install_preserves_existing_instructions(self):
        existing = self.root / ".agents" / "skills" / "my-slides-workflow" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("user edit", encoding="utf-8")
        result = install_agent_workflow(self.root)
        self.assertEqual(existing.read_text(encoding="utf-8"), "user edit")
        self.assertIn(".agents/skills/my-slides-workflow/SKILL.md", result["preserved"])
        claude_skill = self.root / ".claude" / "skills" / "my-slides-workflow" / "SKILL.md"
        self.assertTrue(claude_skill.is_file())

    def test_project_commands_can_resolve_from_nested_directory(self):
        self.init()
        nested = self.root / "nested" / "work"
        nested.mkdir(parents=True)
        original = Path.cwd()
        try:
            import os
            os.chdir(nested)
            self.assertEqual(project_root(None), self.root.resolve())
        finally:
            os.chdir(original)

    def test_wiki_lint_reports_unindexed_topic_page(self):
        self.init()
        (self.base / "wiki" / "company.md").write_text("# Company\n\nA topic page.\n", encoding="utf-8")
        self.assertTrue(any("尚未加入索引" in error for error in validate_wiki(self.base, self.cfg)))
        index = self.base / "wiki" / "index.md"
        index.write_text(index.read_text(encoding="utf-8").replace("## 补充研究", "## 投资概要\n\n- [Company](company.md)\n\n## 补充研究"), encoding="utf-8")
        self.assertEqual(validate_wiki(self.base, self.cfg), [])

    def test_index_sync_adds_configured_chapters_without_overwriting_pages(self):
        self.init()
        index = self.base / "wiki" / "index.md"
        original = index.read_text(encoding="utf-8")
        index.write_text(original + "\nManual note preserved.\n", encoding="utf-8")
        chapters = self.cfg["chapters"] + ["新增章节"]
        sync_wiki_index(index, chapters)
        updated = index.read_text(encoding="utf-8")
        self.assertIn("Manual note preserved.", updated)
        self.assertIn("## 新增章节", updated)
        self.assertIn("## 补充研究", updated)

    def test_source_changes_and_removals_require_acknowledgement(self):
        self.init()
        source = self.root / "memo.md"
        source.write_text("initial", encoding="utf-8")
        _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
        self.assertEqual(pending, ["memo.md"])
        self.assertEqual(removed, [])
        self.assertEqual(mark_ingested(self.base, pending), 1)
        source.unlink()
        for _ in range(2):
            _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
            self.assertEqual(pending, [])
            self.assertEqual(removed, ["memo.md"])
        self.assertEqual(mark_ingested(self.base, removed), 1)
        _, _, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
        self.assertEqual(removed, [])

    def test_report_prepare_captures_a_wiki_content_snapshot(self):
        self.init()
        args = argparse.Namespace(
            project=str(self.root), kind="report", question=None, json=False,
            units=["cover"], changed=False, all_units=False,
        )
        self.assertEqual(prepare(args), 0)
        snapshots = list((self.base / ".state" / "snapshots" / "wiki").glob("*/manifest.json"))
        self.assertEqual(len(snapshots), 1)
        manifest = json.loads(snapshots[0].read_text(encoding="utf-8"))
        self.assertIn("index.md", {item["path"] for item in manifest["files"]})
        task = (self.base / "work" / "report" / "cover.md").read_text(encoding="utf-8")
        self.assertIn("cover", task)


    def test_chart_specs_reject_missing_values_and_incompatible_units(self):
        with self.assertRaisesRegex(ValueError, "缺失值"):
            validate_chart_spec({"type": "bar", "categories": ["A", "B"], "values": [1, None]})
        with self.assertRaisesRegex(ValueError, "单位"):
            validate_chart_spec({"type": "multi-line", "categories": ["A"], "unit": "元", "series": [
                {"name": "收入", "unit": "万元", "values": [1]}
            ]})


    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    def test_pinned_renderers_emit_local_chart_and_icon_svg(self):
        output = render_assets([
            {"id": "chart", "kind": "chart", "spec": {"type": "bar", "title": "Revenue", "categories": ["2024", "2025"], "values": [10, 14], "unit": "亿元"}},
            {"id": "icon", "kind": "icon", "spec": {"name": "arrow-right", "color": "#A6192E", "size": 24}},
        ])
        self.assertIn("<svg", output["chart"])
        self.assertIn("Revenue", output["chart"])
        self.assertIn("<svg", output["icon"])
        self.assertIn("arrow-right", output["icon"])

    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    def test_all_supported_chart_types_render_to_svg(self):
        shared = {"categories": ["A", "B"], "unit": "亿元", "source": "synthetic-source.md"}
        specs = [
            {**shared, "type": "bar", "values": [1, 2]},
            {**shared, "type": "dot", "values": [1, 2]},
            {**shared, "type": "line", "values": [1, 2]},
            {**shared, "type": "multi-line", "series": [{"name": "Actual", "values": [1, 2]}, {"name": "Plan", "values": [2, 3]}]},
            {"type": "scatter", "xUnit": "亿元", "yUnit": "%", "points": [{"x": 1, "y": 20}, {"x": 2, "y": 25}], "source": "synthetic-source.md"},
            {"type": "time-scatter", "xUnit": "date", "yUnit": "亿元", "points": [{"date": "2025-01-01", "y": 1}, {"date": "2025-06-01", "y": 2}], "source": "synthetic-source.md"},
            {**shared, "type": "stacked-bar", "series": [{"name": "A", "values": [1, 2]}, {"name": "B", "values": [2, 3]}]},
            {**shared, "type": "waterfall", "categories": ["Start", "Change", "End"], "values": [10, -2, 8], "totals": [0, 2]},
        ]
        rendered = render_assets([{"id": f"chart-{i}", "kind": "chart", "spec": spec} for i, spec in enumerate(specs)])
        self.assertEqual(len(rendered), 8)
        self.assertTrue(all(value.startswith("<svg") for value in rendered.values()))


    def _notes(self, title="Demo"):
        return (
            f'<script type="application/json" class="slide-notes">'
            f'{{"title":"{title}","script":"Present.","notes":[]}}</script>'
        )

    def test_slide_security_rejects_javascript_entity_bypass(self):
        parser = SlideFragmentParser()
        parser.feed(f'<section class="slide"><a href="java&#9;script:void(window.PWN=1)">x</a>{self._notes()}</section>')
        self.assertTrue(any("不安全链接" in error for error in parser.errors), parser.errors)

    def test_slide_security_rejects_form_action_javascript(self):
        parser = SlideFragmentParser()
        parser.feed(f'<section class="slide"><form action="javascript:void(window.PWN=1)"><button>go</button></form>{self._notes()}</section>')
        self.assertTrue(any("form" in error.lower() for error in parser.errors), parser.errors)

    def test_slide_security_rejects_meta_refresh_and_external_media(self):
        for markup, expected in (
            ('<meta http-equiv="refresh" content="0;url=https://evil.example">', "meta"),
            ('<video poster="https://evil.example/p.png"></video>', "video"),
            ('<svg><image href="https://evil.example/i.png"></image></svg>', "image"),
        ):
            with self.subTest(markup=markup):
                parser = SlideFragmentParser()
                parser.feed(f'<section class="slide">{markup}{self._notes()}</section>')
                self.assertTrue(any(expected in error.lower() for error in parser.errors), parser.errors)


    def test_css_scope_escape_is_rejected(self):
        self.assertEqual(validate_scoped_css("h1{color:red}", label="ok"), [])
        self.assertTrue(any("作用域" in error for error in validate_scoped_css("a{} } b{c:d}", label="x")))

    def test_marker_substring_class_does_not_crash_build(self):
        parser = SlideFragmentParser()
        parser.feed(
            '<section class="slide" data-page-role="cover"><h1>Cover</h1>'
            '<script type="application/json" class="slide-notes old-mls-lucide-spec">'
            '{"title":"Cover","script":"Hi","notes":[]}</script></section>'
        )
        self.assertEqual(parser.errors, [])
        self.assertEqual(len(parser.slides), 1)


    def test_icon_allowlist_requires_list_items_not_embedded_wu(self):
        self.assertEqual(extract_approved_icons("无"), set())
        self.assertEqual(
            extract_approved_icons("- trending-up（无需动画）\n- bar-chart-2\n"),
            {"trending-up", "bar-chart-2"},
        )
        self.assertEqual(extract_approved_icons("- trending-up（无需动画）\n"), {"trending-up"})

    def test_project_yaml_rejects_inline_list_and_strips_comments(self):
        self.init()
        path = self.base / "project.yaml"
        path.write_text(
            'project: "Demo"\nbrand_color: "#A6192E" # 品牌色\nsource_dirs:\n  - "."\n'
            "chapters:\n  - \"投资概要\"\n",
            encoding="utf-8",
        )
        cfg = read_config(path)
        self.assertEqual(cfg["brand_color"], "#A6192E")
        self.assertEqual(cfg["chapters"], ["投资概要"])
        path.write_text(
            'project: "Demo"\nbrand_color: "#A6192E"\nsource_dirs:\n  - "."\n'
            "chapters: [投资概要, 公司概况]\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            read_config(path)
        self.assertIn("行内列表", str(ctx.exception))

    def test_slug_collision_is_detected(self):
        errors = find_slug_collisions(["财务分析/回报分析", "财务分析 回报分析"])
        self.assertTrue(any("slug 冲突" in error for error in errors), errors)
        self.assertEqual(find_slug_collisions(["投资概要", "公司概况"]), [])
        self.init()
        path = self.base / "project.yaml"
        path.write_text(
            'project: "Demo"\nbrand_color: "#A6192E"\nsource_dirs:\n  - "."\n'
            'chapters:\n  - "财务分析/回报分析"\n  - "财务分析 回报分析"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx:
            read_config(path)
        self.assertIn("slug 冲突", str(ctx.exception))

    def test_chart_spec_rejects_bad_date_and_dimensions(self):
        with self.assertRaises(ValueError) as ctx:
            validate_chart_spec(
                {
                    "type": "time-scatter",
                    "xUnit": "日期",
                    "yUnit": "%",
                    "points": [{"date": "not-a-date", "y": 1.0}],
                }
            )
        self.assertIn("date", str(ctx.exception).lower())
        with self.assertRaises(ValueError) as ctx:
            validate_chart_spec(
                {
                    "type": "bar",
                    "categories": ["A"],
                    "values": [1],
                    "width": 10,
                    "height": 10,
                }
            )
        self.assertIn("宽高", str(ctx.exception))
        validate_chart_spec(
            {
                "type": "time-scatter",
                "xUnit": "日期",
                "yUnit": "%",
                "points": [{"date": "2024-01-15", "y": 1.0}],
            }
        )

    def test_json_mode_errors_emit_json_object(self):
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "doctor", "--project", "/no/such/path", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout.strip() or result.stderr.strip())
        self.assertIn("error", payload)
        self.assertTrue(payload["error"])

    def test_init_defaults_to_v2_without_chapters_path(self):
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.assertTrue((self.base / "units.json").is_file())
        self.assertTrue((self.base / "reports" / "units").is_dir())
        self.assertTrue((self.base / "slides" / "pages").is_dir())
        self.assertFalse((self.base / "slides" / "chapters").exists())
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "status", "--project", str(self.root), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["format_version"], "v2")
        self.assertFalse(payload.get("deprecated"))

    def test_legacy_project_without_units_is_refused(self):
        self.init()
        self.remove_units_manifest()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        status = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "status", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(status.returncode, 1)
        payload = json.loads(status.stdout)
        self.assertTrue(payload["deprecated"])
        self.assertIn("units.json", payload["deprecation_warning"])
        refused = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "prepare", "report", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn("units.json", json.loads(refused.stdout).get("error", ""))
        doctor = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "doctor", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(doctor.returncode, 1)
        self.assertFalse(json.loads(doctor.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
