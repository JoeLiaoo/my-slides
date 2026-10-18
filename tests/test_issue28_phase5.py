"""Issue #28 phase 5: all-step handoff, Agent doctor, and safe cleanup."""
import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from my_slides.agent_workflow import check_agent_workflow, install_agent_workflow
from my_slides.commands import clean, next_step
from my_slides.commands.init import init_project
from my_slides.cli import build_parser


class Issue28Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    def tearDown(self):
        self.temp.cleanup()

    def test_next_all_groups_current_pending_steps_by_actor(self):
        args = build_parser().parse_args(["next", "--all", "--json", "--project", str(self.root)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(next_step.run(args), 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data["steps"])
        self.assertEqual(data["steps"], data["by_actor"]["agent"] + data["by_actor"]["human"])
        self.assertTrue(all(step["actor"] == "agent" for step in data["by_actor"]["agent"]))

    def test_agent_doctor_reports_current_then_outdated_install(self):
        install_agent_workflow(self.root)
        current = check_agent_workflow(self.root)
        self.assertTrue(current["ok"])
        target = self.root / ".agents/skills/my-slides-workflow/SKILL.md"
        target.write_text("user-edited", encoding="utf-8")
        status = check_agent_workflow(self.root)
        self.assertFalse(status["ok"])
        self.assertEqual(status["files"][0]["status"], "outdated")

    def test_clean_defaults_to_preview_and_yes_removes_only_expired_items(self):
        old_handoff = self.base / "work" / "reports" / "old.md"
        old_handoff.parent.mkdir(parents=True)
        old_handoff.write_text("old handoff", encoding="utf-8")
        old_snapshot = self.base / ".state/snapshots/wiki/20200101T000000Z"
        old_snapshot.mkdir(parents=True)
        (old_snapshot / "index.md").write_text("old snapshot", encoding="utf-8")
        old = 1_600_000_000
        for path in (old_handoff, old_handoff.parent, old_snapshot / "index.md", old_snapshot):
            os.utime(path, (old, old))
        preview = build_parser().parse_args(["clean", "--json", "--project", str(self.root)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            clean.run(preview)
        data = json.loads(out.getvalue())
        self.assertTrue(data["preview"])
        self.assertEqual(len(data["candidates"]), 2)
        self.assertTrue(old_handoff.exists())
        execute = build_parser().parse_args(["clean", "--json", "--yes", "--project", str(self.root)])
        with contextlib.redirect_stdout(io.StringIO()):
            clean.run(execute)
        self.assertFalse(old_handoff.parent.exists())
        self.assertFalse(old_snapshot.exists())


if __name__ == "__main__":
    unittest.main()
