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
from scripts.check_pr_version import (
    changelog_has_version,
    create_missing_tags,
    is_one_step_bump,
    is_skippable_change,
    validate_main_advance,
    validate_version_change,
)


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

    def test_skips_only_ci_test_and_script_paths(self):
        self.assertTrue(is_skippable_change([".github/workflows/ci.yml", "tests/test_cli.py", "scripts/check_pr_version.py"]))
        self.assertFalse(is_skippable_change(["tests/test_cli.py", "src/my_slides/cli.py"]))
        self.assertFalse(is_skippable_change([]))

    def test_main_advance_allows_unchanged_skippable_push_and_rejects_a_stuck_version(self):
        changelog = "## [0.2.11]\n\n### Added\n- Note.\n"
        self.assertEqual(validate_main_advance("0.2.11", "0.2.11", ["tests/test_cli.py"], changelog), [])
        errors = validate_main_advance("0.2.11", "0.2.11", ["src/my_slides/cli.py"], changelog)
        self.assertTrue(any("仍是 0.2.11" in error for error in errors))
        self.assertEqual(validate_main_advance("0.2.10", "0.2.11", ["src/my_slides/cli.py"], changelog), [])

    def test_parser_build_does_not_read_git(self):
        from my_slides.cli import build_parser

        with patch("my_slides.cli.format_version", side_effect=AssertionError("read too early")):
            build_parser()

    def test_tagging_is_repeatable_and_refuses_a_conflicting_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init")
            self._git(root, "config", "user.email", "test@example.com")
            self._git(root, "config", "user.name", "Test")
            self._commit_version(root, "0.1.0", "## [0.1.0]\n\n### Added\n- Start.\n")
            first = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self._commit_version(root, "0.2.0", "## [0.1.0]\n\n### Added\n- Start.\n\n## [0.2.0]\n\n### Changed\n- Next.\n")
            second = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(create_missing_tags(root, push=False), 0)
            self.assertEqual(self._git(root, "rev-parse", "v0.1.0^{commit}").stdout.strip(), first)
            self.assertEqual(self._git(root, "rev-parse", "v0.2.0^{commit}").stdout.strip(), second)
            self.assertEqual(create_missing_tags(root, push=False), 0)
            self._git(root, "tag", "-d", "v0.2.0")
            self._git(root, "tag", "-a", "v0.2.0", first, "-m", "wrong")
            self.assertEqual(create_missing_tags(root, push=False), 1)

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8")

    def _commit_version(self, root: Path, version: str, changelog: str) -> None:
        (root / "pyproject.toml").write_text(f'[project]\nname = "my-slides"\nversion = "{version}"\n', encoding="utf-8")
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        self._git(root, "add", "pyproject.toml", "CHANGELOG.md")
        self._git(root, "commit", "-m", f"version {version}")


if __name__ == "__main__":
    unittest.main()
