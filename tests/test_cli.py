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
        self.assertFalse((self.base / "slides").exists())
        self.assertFalse((self.base / "specs").exists())
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
