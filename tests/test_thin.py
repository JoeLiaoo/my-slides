import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides import thin


class ThinWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / "my-slides"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **extra):
        return argparse.Namespace(project=str(self.root), json=True, target=None, legacy=False,
                                  force=False, source_dir=None, **extra)

    def config(self, present):
        self.base.mkdir(exist_ok=True)
        (self.base / "project.json").write_text(json.dumps({
            "schema_version": 1, "article": "my-slides/article.md", "present": present,
        }), encoding="utf-8")

    def present(self, target=None):
        args = self.args()
        args.target = target
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = thin.present(args)
        return code, json.loads(output.getvalue())

    def dual_outputs(self):
        # Put slides first so an uncaught engine failure cannot hide behind a
        # previously emitted beautiful result.
        self.config({
            "slides": {"provider": "design-and-slides", "output": "my-slides/design/deck"},
            "beautiful": {"provider": "beautiful-article", "output": "my-slides/beautiful/article.html"},
        })
        (self.base / "article.md").write_text("# 正文\nSource: example", encoding="utf-8")
        deck = self.base / "design" / "deck"
        deck.mkdir(parents=True)
        (deck / "deck.json").write_text("{}", encoding="utf-8")
        html = self.base / "beautiful" / "article.html"
        html.parent.mkdir()
        html.write_text("<html>human edit</html>", encoding="utf-8")
        return deck, html

    def test_init_creates_only_thin_config_and_never_overwrites(self):
        self.assertEqual(thin.init(self.args()), 0)
        self.assertEqual(thin.read_project(self.root)["present"], {})
        self.assertFalse((self.base / "units.json").exists())
        with self.assertRaisesRegex(ValueError, "未覆盖"):
            thin.init(self.args())

    def test_config_rejects_unsupported_schema_and_path_escape(self):
        self.config({})
        data = json.loads((self.base / "project.json").read_text())
        data["schema_version"] = 2
        (self.base / "project.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "schema_version"):
            thin.read_project(self.root)
        self.config({"beautiful": {"provider": "beautiful-article", "output": "../outside.html"}})
        with self.assertRaisesRegex(ValueError, "越界"):
            thin.read_project(self.root)
        self.config({"beautiful": {"provider": "beautiful-article", "output": "my-slides"}})
        with self.assertRaisesRegex(ValueError, "重叠"):
            thin.read_project(self.root)

    def test_present_failure_isolates_targets_and_preserves_output(self):
        self.config({
            "beautiful": {"provider": "beautiful-article", "output": "my-slides/beautiful/article.html"},
            "slides": {"provider": "design-and-slides", "output": "my-slides/design/deck"},
        })
        (self.base / "article.md").write_text("# Existing article\nSource: example", encoding="utf-8")
        html = self.base / "beautiful" / "article.html"
        html.parent.mkdir()
        html.write_text("<html>human edit</html>", encoding="utf-8")
        with patch.object(thin, "design_status", return_value={"ready": False, "env": "MY_SLIDES_DESIGN_ROOT"}):
            self.assertEqual(thin.present(self.args()), 1)
        self.assertEqual(html.read_text(), "<html>human edit</html>")
        with patch.object(thin, "design_status", side_effect=AssertionError("slides must not run")):
            args = self.args()
            args.target = "beautiful"
            self.assertEqual(thin.present(args), 1)
        self.assertEqual(html.read_text(), "<html>human edit</html>")

    def test_design_check_success_means_structure_only(self):
        self.config({"slides": {"provider": "design-and-slides", "output": "my-slides/design/deck"}})
        (self.base / "article.md").write_text("# Article", encoding="utf-8")
        deck = self.base / "design" / "deck"
        deck.mkdir(parents=True)
        (deck / "deck.json").write_text("{}", encoding="utf-8")
        with patch.object(thin, "design_status", return_value={"ready": True}), \
                patch.object(thin, "run_agent", return_value=(0, {"ok": True})) as check:
            self.assertEqual(thin.present(self.args()), 0)
        check.assert_called_once_with(["check", "deck", "--strict"], deck.parent)

    def test_engine_failures_are_per_target_and_never_write_artifacts(self):
        deck, html = self.dual_outputs()
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        for error in (subprocess.TimeoutExpired("Design", 1), OSError("unavailable"),
                      ValueError("invalid JSON"), RuntimeError("check failed")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(thin, "design_status", return_value={"ready": True}), \
                    patch.object(thin, "run_agent", side_effect=error):
                code, result = self.present()
                self.assertEqual(code, 1)
                self.assertFalse(result["complete"])
                self.assertEqual(result["targets"]["slides"]["status"], "failed")
                self.assertEqual(result["targets"]["beautiful"]["status"], "pending_agent")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_output_read_and_dependency_probe_failures_are_isolated(self):
        self.dual_outputs()
        fingerprint = thin._fingerprint

        def unreadable(path):
            if path.name == "deck":
                raise PermissionError("unreadable deck")
            return fingerprint(path)

        for target, effect in (("_fingerprint", unreadable), ("design_status", OSError("probe failed"))):
            with self.subTest(target=target), patch.object(thin, target, side_effect=effect):
                code, result = self.present()
                self.assertEqual(code, 1)
                self.assertEqual(result["targets"]["slides"]["status"], "failed")
                self.assertEqual(result["targets"]["beautiful"]["status"], "pending_agent")

    def test_content_sync_remains_unknown_after_article_changes(self):
        deck, html = self.dual_outputs()
        before = (deck / "deck.json").read_bytes(), html.read_bytes()
        hashes = []
        with patch.object(thin, "design_status", return_value={"ready": True}), \
                patch.object(thin, "run_agent", return_value=(0, {"ok": True})):
            for article in ("# First claim", "# Different claim"):
                (self.base / "article.md").write_text(article, encoding="utf-8")
                code, result = self.present("slides")
                self.assertEqual(code, 0)
                self.assertEqual(set(result["targets"]), {"slides"})
                self.assertEqual(result["completion_scope"], "deterministic_checks_only")
                slides = result["targets"]["slides"]
                self.assertEqual(slides["completion"], "structure_check_only")
                self.assertEqual(slides["content_sync"], "unknown")
                self.assertEqual(slides["render"], "not_run")
                self.assertEqual(slides["human_review"], "not_done")
                self.assertEqual(slides["article_sha256"], hashlib.sha256(article.encode()).hexdigest())
                hashes.append(slides["article_sha256"])
        self.assertNotEqual(*hashes)
        self.assertEqual(before, ((deck / "deck.json").read_bytes(), html.read_bytes()))

    def test_missing_whitespace_and_invalid_utf8_article_fail_each_target(self):
        self.dual_outputs()
        article = self.base / "article.md"
        for content in (None, b"", b" \n\t", b"\xef\xbb\xbf \n", b"\xff"):
            with self.subTest(content=content), patch.object(thin, "run_agent") as check:
                if content is None:
                    article.unlink()
                else:
                    article.write_bytes(content)
                code, result = self.present()
                self.assertEqual(code, 1)
                self.assertTrue(all(r["status"] == "failed" for r in result["targets"].values()))
                check.assert_not_called()

    def test_empty_disabled_and_invalid_provider_targets(self):
        self.config({})
        with self.assertRaisesRegex(ValueError, "尚未选择"):
            self.present()
        with self.assertRaisesRegex(ValueError, "未在"):
            self.present("slides")
        self.config({"beautiful": {"provider": "fake", "output": "my-slides/a.html"}})
        with self.assertRaisesRegex(ValueError, "provider"):
            thin.read_project(self.root)

    def test_outputs_cannot_overlap_article_config_or_each_other(self):
        for path in ("my-slides/article.md", "my-slides/project.json", "my-slides/design/deck/a.html"):
            with self.subTest(path=path):
                self.config({
                    "slides": {"provider": "design-and-slides", "output": "my-slides/design/deck"},
                    "beautiful": {"provider": "beautiful-article", "output": path},
                })
                with self.assertRaisesRegex(ValueError, "重叠"):
                    thin.read_project(self.root)

    def symlink(self, link, target, is_dir=False):
        try:
            link.symlink_to(target, target_is_directory=is_dir)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable")
            raise

    def test_redirected_workspace_cannot_write_or_read_external_config(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external).resolve()
            self.symlink(self.base, outside, True)
            with self.assertRaisesRegex(ValueError, "越界"):
                thin.init(self.args())
            self.assertFalse((outside / "project.json").exists())
            with self.assertRaisesRegex(ValueError, "越界"):
                thin.read_project(self.root)

    def test_dangling_config_link_is_not_overwritten(self):
        self.base.mkdir()
        target = self.root / "missing.json"
        self.symlink(self.base / "project.json", target)
        with self.assertRaisesRegex(ValueError, "未覆盖"):
            thin.init(self.args())
        self.assertFalse(target.exists())

    def test_config_alias_cannot_be_used_as_article(self):
        self.config({})
        original = self.base / "project.json"
        alias = self.base / "config.json"
        original.rename(alias)
        self.symlink(original, alias)
        data = json.loads(alias.read_text(encoding="utf-8"))
        data["article"] = "my-slides/config.json"
        alias.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "article"):
            thin.read_project(self.root)

    def test_link_in_deck_is_failed_without_reading_external_file(self):
        deck, html = self.dual_outputs()
        external = self.root / "source.txt"
        external.write_text("read-only source", encoding="utf-8")
        self.symlink(deck / "linked.txt", external)
        with patch.object(thin, "run_agent") as check:
            code, result = self.present()
        self.assertEqual(code, 1)
        self.assertEqual(result["targets"]["slides"]["status"], "failed")
        self.assertEqual(result["targets"]["beautiful"]["status"], "pending_agent")
        check.assert_not_called()

    def test_legacy_flags_require_explicit_legacy_mode(self):
        args = self.args()
        args.force = True
        with self.assertRaisesRegex(ValueError, "--legacy"):
            thin.init(args)
        self.assertFalse(self.base.exists())
        args.legacy = True
        with patch("my_slides.commands.init.init_project", return_value=0) as legacy:
            self.assertEqual(thin.init(args), 0)
        legacy.assert_called_once_with(args)

    def test_cli_discovers_thin_project_from_nested_unicode_directory(self):
        self.config({"beautiful": {"provider": "beautiful-article", "output": "my-slides/a.html"}})
        (self.base / "article.md").write_text("# 已有正文", encoding="utf-8")
        nested = self.base / "中文 空格"
        nested.mkdir()
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        result = subprocess.run([sys.executable, "-m", "my_slides.cli", "present", "--json"],
                                cwd=nested, env=env, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["targets"]["beautiful"]["status"], "pending_agent")


if __name__ == "__main__":
    unittest.main()
