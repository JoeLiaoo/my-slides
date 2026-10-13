"""Tests for ``scripts/sync-skill-templates.py`` — keeps skill text in step with the wheel mirror."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class SyncSkillTemplatesTests(unittest.TestCase):
    def run_sync(self, *args: str) -> subprocess.CompletedProcess[str]:
        script = REPO_ROOT / "scripts" / "sync-skill-templates.py"
        return subprocess.run(
            [sys.executable, str(script), *args, "--repo", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_check_succeeds_after_force_sync(self):
        force = self.run_sync("--force")
        self.assertEqual(force.returncode, 0, force.stdout + force.stderr)
        check = self.run_sync("--check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_check_fails_when_drifted(self):
        # Force sync first, then introduce drift in the packaged mirror.
        self.run_sync("--force")
        packaged = REPO_ROOT / "src" / "my_slides" / "templates" / "references" / "wiki.md"
        backup = packaged.read_text(encoding="utf-8")
        try:
            packaged.write_text(backup + "\nExtra drift.\n", encoding="utf-8")
            check = self.run_sync("--check")
            self.assertEqual(check.returncode, 2)
            self.assertIn("drift", check.stderr)
        finally:
            packaged.write_text(backup, encoding="utf-8")
        # ``--force`` must reset the mirror.
        self.run_sync("--force")
        second = self.run_sync("--check")
        self.assertEqual(second.returncode, 0)

    def test_force_refuses_when_drifted_without_force(self):
        self.run_sync("--force")
        packaged = REPO_ROOT / "src" / "my_slides" / "templates" / "my-slides-workflow.md"
        backup = packaged.read_text(encoding="utf-8")
        try:
            packaged.write_text(backup + "\n", encoding="utf-8")
            no_force = self.run_sync()
            self.assertEqual(no_force.returncode, 3)
        finally:
            packaged.write_text(backup, encoding="utf-8")
        self.run_sync("--force")


if __name__ == "__main__":
    unittest.main()
