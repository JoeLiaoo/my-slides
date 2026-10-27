import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides import thin


class ThinWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
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


if __name__ == "__main__":
    unittest.main()
