from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from my_slides import __version__, format_version, git_metadata
from scripts.check_pr_version import changelog_has_version, is_one_step_bump, validate_version_change


class GitVersionMetadataTests(unittest.TestCase):
    def _project(self, root: Path) -> None:
        (root / "pyproject.toml").write_text('[project]\nname = "my-slides"\nversion = "0.2.11"\n', encoding="utf-8")

    def test_formal_install_without_source_metadata_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            commit, dirty = git_metadata(Path(tmp))
        self.assertIsNone(commit)
        self.assertIsNone(dirty)

    def test_unavailable_git_falls_back_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            with patch("my_slides.subprocess.run", side_effect=FileNotFoundError("git")):
                self.assertEqual(git_metadata(root), (None, None))

    def test_clean_and_dirty_checkout_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            responses = [
                SimpleNamespace(stdout=f"{root}\n"),
                SimpleNamespace(stdout="abc1234\n"),
                SimpleNamespace(stdout=""),
            ]
            with patch("my_slides.subprocess.run", side_effect=responses):
                self.assertEqual(git_metadata(root), ("abc1234", False))
            responses[-1] = SimpleNamespace(stdout=" M README.md\n")
            with patch("my_slides.subprocess.run", side_effect=responses):
                self.assertEqual(git_metadata(root), ("abc1234", True))

    def test_version_output_formats_commit_and_dirty_marker(self):
        with patch("my_slides.git_metadata", return_value=(None, None)):
            self.assertEqual(format_version(), f"my-slides {__version__}")
        with patch("my_slides.git_metadata", return_value=("abc1234", False)):
            self.assertEqual(format_version(), f"my-slides {__version__} (abc1234)")
        with patch("my_slides.git_metadata", return_value=("abc1234", True)):
            self.assertEqual(format_version(), f"my-slides {__version__} (abc1234, 有未提交修改)")

    def test_help_json_includes_commit_metadata(self):
        repo = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": str(repo / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "help", "--json"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["version"], __version__)
        self.assertIn("commit", payload)
        self.assertIn("dirty", payload)


class VersionPolicyTests(unittest.TestCase):
    def test_accepts_one_patch_or_minor_step(self):
        self.assertTrue(is_one_step_bump("0.2.10", "0.2.11"))
        self.assertTrue(is_one_step_bump("0.2.10", "0.3.0"))

    def test_rejects_same_version_and_skipped_steps(self):
        self.assertFalse(is_one_step_bump("0.2.10", "0.2.10"))
        self.assertFalse(is_one_step_bump("0.2.10", "0.2.12"))
        self.assertFalse(is_one_step_bump("0.2.10", "0.4.0"))

    def test_major_step_requires_maintainer_authorization(self):
        self.assertFalse(is_one_step_bump("0.2.10", "1.0.0"))
        self.assertTrue(is_one_step_bump("0.2.10", "1.0.0", allow_major=True))

    def test_requires_matching_changelog_heading(self):
        changelog = "## [0.2.11] - Pending\n\n### Fixed\n- Fix.\n"
        self.assertTrue(changelog_has_version(changelog, "0.2.11"))
        self.assertFalse(changelog_has_version("## [0.2.11] - Pending\n<!-- TODO -->\n", "0.2.11"))
        self.assertEqual(validate_version_change("0.2.10", "0.2.11", changelog), [])
        errors = validate_version_change("0.2.10", "0.2.11", "## [Unreleased]\n")
        self.assertTrue(any("CHANGELOG.md 缺少非空版本条目" in error for error in errors))

    def test_breaking_changelog_requires_minor_step_and_vice_versa(self):
        patch_changelog = "## [0.2.11]\n\n### Breaking Changes\n- Changed a command.\n"
        errors = validate_version_change("0.2.10", "0.2.11", patch_changelog)
        self.assertTrue(any("请升 minor" in error for error in errors))
        minor_changelog = "## [0.3.0]\n\n### Changed\n- Changed a command.\n"
        errors = validate_version_change("0.2.10", "0.3.0", minor_changelog)
        self.assertTrue(any("minor/major 升版" in error for error in errors))

    def test_rejects_invalid_version_syntax(self):
        errors = validate_version_change("0.2.10", "0.2.11rc1", "## [0.2.11rc1]\n")
        self.assertTrue(any("X.Y.Z" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
