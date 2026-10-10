"""Approval handoff and next-step behavior at the CLI command boundary."""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides.commands import approve, confirm, next_step, status
from my_slides.commands.init import init_project
from my_slides.state import mark_report_approved, read_unit_state
from my_slides.unit_workflow import assemble_after_report_approvals
from my_slides.units import Unit, unit_paths, write_units_manifest


class ApprovalCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.unit = Unit(id="cover", chapter="投资概要", role="cover")
        write_units_manifest(self.base, [self.unit])
        self.paths = unit_paths(self.base, self.unit.id)
        self.paths.report.write_text(
            "# Cover\n\nA supported investment summary with enough detail for review.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def request(self, kind="report"):
        args = argparse.Namespace(
            project=str(self.root), kind=kind, units=["cover"], changed=False,
            all_units=False, json=True,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approve.run(args), 0)
        return read_unit_state(self.base, "cover")[kind]["pending_approval"]

    def next_action(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(next_step.run(argparse.Namespace(project=str(self.root), json=True)), 0)
        return json.loads(out.getvalue())["next"]

    def confirm(self, answers, kind="report"):
        args = argparse.Namespace(project=str(self.root), kind=kind, unit="cover")
        with patch("my_slides.commands.confirm.sys") as terminal, \
             patch("my_slides.commands.confirm.getpass.getuser", return_value="review-account"), \
             patch("builtins.input", side_effect=answers), \
             contextlib.redirect_stdout(io.StringIO()):
            terminal.stdin.isatty.return_value = True
            terminal.stdout.isatty.return_value = True
            return confirm.run(args)

    def test_noninteractive_confirmation_is_rejected(self):
        self.request()
        with patch("my_slides.commands.confirm.sys") as terminal:
            terminal.stdin.isatty.return_value = False
            terminal.stdout.isatty.return_value = True
            with self.assertRaisesRegex(ValueError, "交互终端"):
                confirm.run(argparse.Namespace(project=str(self.root), kind="report", unit="cover"))
        self.assertFalse(read_unit_state(self.base, "cover")["report"]["current"])

    def test_next_hands_off_then_advances_only_after_confirmation(self):
        request = self.request()
        waiting = self.next_action()
        self.assertEqual(waiting["actor"], "human")
        self.assertEqual(waiting["unit"], "cover")
        self.assertIn("review report --unit cover", waiting["command"])
        phrase = f"APPROVE REPORT cover {request['content_sha256'][:12]}"
        self.assertEqual(self.confirm(["Human Reviewer", phrase]), 0)
        approved = read_unit_state(self.base, "cover")["report"]
        self.assertTrue(approved["current"])
        self.assertEqual(approved["approved_by"], "Human Reviewer")
        self.assertEqual(approved["approved_account"], "review-account")
        self.assertIsNone(approved["pending_approval"])
        self.assertIn("my-slides assemble", self.next_action()["command"])

    def test_empty_reviewer_and_wrong_phrase_do_not_approve(self):
        self.request()
        for answers, expected in [([""], "不能为空"), (["Reviewer", "WRONG"], "不匹配")]:
            with self.subTest(answers=answers):
                with self.assertRaisesRegex(ValueError, expected):
                    self.confirm(answers)
                state = read_unit_state(self.base, "cover")["report"]
                self.assertIsNone(state["approved_sha256"])
                self.assertIsNotNone(state["pending_approval"])

    def test_spec_confirmation_is_a_separate_human_step(self):
        request = self.request()
        self.confirm(["Reviewer", f"APPROVE REPORT cover {request['content_sha256'][:12]}"])
        _, errors = assemble_after_report_approvals(self.base)
        self.assertEqual(errors, [])
        self.paths.spec.write_text(
            "## Slide 1 — Cover\n页面 ID：cover\n页面角色：cover\n"
            "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
            "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
            "### 布局意图\nLayout.\n### 图标需求\n无\n",
            encoding="utf-8",
        )
        self.assertIn("approve spec --unit cover", self.next_action()["command"])
        request = self.request("spec")
        self.assertEqual(self.next_action()["actor"], "human")
        self.assertIn("review spec --unit cover", self.next_action()["command"])
        self.confirm(["Reviewer", f"APPROVE SPEC cover {request['content_sha256'][:12]}"], kind="spec")
        self.assertTrue(read_unit_state(self.base, "cover")["spec"]["current"])
        self.assertIn("prepare slides --unit cover", self.next_action()["command"])

    def test_changed_report_or_dependency_invalidates_request(self):
        for changed_dependency in (False, True):
            with self.subTest(changed_dependency=changed_dependency):
                wiki = self.base / "wiki" / "evidence.md"
                wiki.write_text("# Evidence\n\nVersion one.\n", encoding="utf-8")
                self.paths.report.write_text(
                    "# Cover\n\nInvestment conclusion backed by [evidence](../../wiki/evidence.md).\n",
                    encoding="utf-8",
                )
                request = self.request()
                if changed_dependency:
                    wiki.write_text("# Evidence\n\nVersion two.\n", encoding="utf-8")
                else:
                    self.paths.report.write_text(
                        self.paths.report.read_text(encoding="utf-8") + "New conclusion.\n",
                        encoding="utf-8",
                    )
                phrase = f"APPROVE REPORT cover {request['content_sha256'][:12]}"
                with self.assertRaisesRegex(ValueError, "申请后内容/依赖已变化"):
                    self.confirm(["Reviewer", phrase])
                self.assertFalse(read_unit_state(self.base, "cover")["report"]["current"])

    def test_legacy_approval_is_visible_and_cannot_assemble(self):
        mark_report_approved(self.base, self.unit, when="legacy", project_root=self.root)
        action = self.next_action()
        self.assertEqual(action["actor"], "agent")
        self.assertIn("approve report --unit cover", action["command"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status.run(argparse.Namespace(project=str(self.root), units=None, json=True))
        report = json.loads(out.getvalue())["approvals"]["report"]
        self.assertFalse(report["current"])
        self.assertEqual(report["unattributed_units"], ["cover"])
        _, errors = assemble_after_report_approvals(self.base)
        self.assertTrue(any("审阅者" in error for error in errors), errors)
        self.assertFalse((self.base / "reports" / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
