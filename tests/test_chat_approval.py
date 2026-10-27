"""Conversation approval and chapter-scoped confirmation."""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from my_slides.commands import approve, confirm, next_step, review
from my_slides.commands.init import init_project
from my_slides.state import read_unit_state, refresh_unit_currency
from my_slides.units import Unit, unit_paths, write_units_manifest



class ChatApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + 'reviewer: "张三"\n', encoding="utf-8")
        self.units = [
            Unit(id="cover", chapter="投资概要", role="cover", title="封面"),
            Unit(id="demand", chapter="行业分析", role="content", title="需求分析"),
            Unit(id="competition", chapter="行业分析", role="content", title="竞争分析"),
        ]
        write_units_manifest(self.base, self.units)
        for unit in self.units:
            report = f"# {unit.title}\n\nEnough report text for {unit.id} to pass validation.\n"
            unit_paths(self.base, unit.id).report.write_text(report, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def approve_chapter(self, kind="report"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = approve.run(argparse.Namespace(
                project=str(self.root), kind=kind, units=None, changed=False,
                all_units=False, chapter="行业分析", json=True,
            ))
        self.assertEqual(code, 0, out.getvalue())

    def review_json(self, kind="report", unit=None, chapter=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = review.run(argparse.Namespace(
                project=str(self.root), kind=kind, json=True, unit=unit, chapter=chapter,
            ))
        self.assertEqual(code, 0, out.getvalue())
        return json.loads(out.getvalue())

    def confirm_chat(self, kind, phrase, reply="行业分析这两节可以，批准", **scope):
        args = argparse.Namespace(
            project=str(self.root), kind=kind, via="chat", phrase=phrase,
            user_reply=reply, reviewer=None, unit=scope.get("unit"), chapter=scope.get("chapter"),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            return confirm.run(args)

    def test_chat_confirmation_records_reply_and_archive(self):
        self.approve_chapter()
        packet = self.review_json(chapter="行业分析")
        self.assertEqual(packet["scope"], "chapter")
        self.assertTrue(packet["phrase"].startswith("APPROVE REPORT 行业分析 "))
        self.assertEqual(self.confirm_chat("report", packet["phrase"], chapter="行业分析"), 0)
        for unit_id in ("demand", "competition"):
            state = read_unit_state(self.base, unit_id)["report"]
            self.assertTrue(state["current"])
            self.assertEqual(state["approval_channel"], "chat")
            self.assertEqual(state["user_reply"], "行业分析这两节可以，批准")
            self.assertEqual(state["approved_by"], "张三")
            archive = self.base / ".state" / "approved" / "report" / unit_id / f"{state['approved_sha256']}.md"
            self.assertTrue(archive.is_file())
        self.assertFalse(read_unit_state(self.base, "cover")["report"]["current"])

    def test_wrong_phrase_and_stale_content_do_not_approve(self):
        self.approve_chapter()
        packet = self.review_json(chapter="行业分析")
        with self.assertRaisesRegex(ValueError, "短语"):
            self.confirm_chat("report", "APPROVE REPORT 行业分析 000000000000", chapter="行业分析")
        unit_paths(self.base, "demand").report.write_text(
            unit_paths(self.base, "demand").report.read_text(encoding="utf-8") + "补充一句。\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "内容已变化"):
            self.confirm_chat("report", packet["phrase"], chapter="行业分析")
        self.assertFalse(read_unit_state(self.base, "demand")["report"]["current"])

    def test_terminal_mode_rejects_chat_confirmation(self):
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "approval_mode: terminal\n", encoding="utf-8")
        self.approve_chapter()
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.confirm_chat("report", "APPROVE REPORT 行业分析 000000000000", chapter="行业分析")

    def test_chapter_approval_then_one_edit_stays_local(self):
        self.approve_chapter()
        packet = self.review_json(chapter="行业分析")
        self.confirm_chat("report", packet["phrase"], chapter="行业分析")
        report = unit_paths(self.base, "demand").report
        report.write_text(report.read_text(encoding="utf-8") + "补充一句。\n", encoding="utf-8")
        demand = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
        other = refresh_unit_currency(self.base, self.units[2], project_root=self.root)
        self.assertFalse(demand["report"]["current"])
        self.assertTrue(other["report"]["current"])

    def test_next_asks_for_review_in_chat_mode(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(approve.run(argparse.Namespace(
                project=str(self.root), kind="report", units=["cover"], changed=False,
                all_units=False, chapter=None, json=True,
            )), 0)
        cover = self.review_json(unit="cover")
        self.confirm_chat("report", cover["phrase"], reply="封面报告批准", unit="cover")
        self.approve_chapter()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(next_step.run(argparse.Namespace(project=str(self.root), json=True)), 0)
        step = json.loads(out.getvalue())["next"]
        self.assertEqual(step["actor"], "human")
        self.assertIn("review report --unit demand", step["command"])

    def test_review_shows_pending_text_and_marks_truncated_report_diffs(self):
        self.approve_chapter()
        packet = self.review_json(unit="demand")
        body = unit_paths(self.base, "demand").report.read_text(encoding="utf-8")
        self.assertEqual(packet["units"][0]["content"], body)
        self.assertIn("没有可对比", packet["units"][0]["changes"]["summary"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(review.run(argparse.Namespace(
                project=str(self.root), kind="report", json=False, unit="demand", chapter=None,
            )), 0)
        human = out.getvalue()
        self.assertIn("待审正文", human)
        self.assertIn(body.strip(), human)

        self.confirm_chat("report", packet["phrase"], reply="需求分析报告批准", unit="demand")
        report = unit_paths(self.base, "demand").report
        report.write_text(report.read_text(encoding="utf-8") + "".join(f"\nchanged line {index}" for index in range(80)), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approve.run(argparse.Namespace(
                project=str(self.root), kind="report", units=["demand"], changed=False,
                all_units=False, chapter=None, json=True,
            )), 0)
        again = self.review_json(unit="demand")
        self.assertTrue(again["units"][0]["changes"]["truncated"])
        self.assertIn("差异已截断，仅显示前 40 行", again["units"][0]["changes"]["diff"])
        self.assertIn("changed line 0", again["units"][0]["content"])

    def test_old_phrase_rejects_a_later_chapter_or_dependency_context(self):
        from my_slides.project import read_config
        from my_slides.unit_management import move_unit

        self.approve_chapter()
        phrase = self.review_json(unit="demand")["phrase"]
        chapters = [str(item) for item in read_config(self.base / "project.yaml")["chapters"]]
        move_unit(self.base, "demand", chapters, chapter="公司概况")
        with self.assertRaisesRegex(ValueError, "短语"):
            self.confirm_chat("report", phrase, unit="demand")

        wiki = self.base / "wiki" / "evidence.md"
        wiki.write_text("# Evidence\n\nVersion one.\n", encoding="utf-8")
        unit_paths(self.base, "competition").report.write_text(
            "# 竞争分析\n\nConclusion backed by [evidence](../../wiki/evidence.md).\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approve.run(argparse.Namespace(
                project=str(self.root), kind="report", units=["competition"], changed=False,
                all_units=False, chapter=None, json=True,
            )), 0)
        first = self.review_json(unit="competition")["phrase"]
        wiki.write_text("# Evidence\n\nVersion two.\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approve.run(argparse.Namespace(
                project=str(self.root), kind="report", units=["competition"], changed=False,
                all_units=False, chapter=None, json=True,
            )), 0)
        second = self.review_json(unit="competition")["phrase"]
        self.assertNotEqual(first, second)
        with self.assertRaisesRegex(ValueError, "短语"):
            self.confirm_chat("report", first, unit="competition")
        self.assertEqual(self.confirm_chat("report", second, reply="依赖更新后批准", unit="competition"), 0)

    def test_init_force_keeps_approval_settings(self):
        from my_slides.project import read_config

        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + 'approval_mode: "terminal"\n', encoding="utf-8")
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=True, json=False))
        cfg = read_config(config)
        self.assertEqual(cfg["approval_mode"], "terminal")
        self.assertEqual(cfg["reviewer"], "张三")


if __name__ == "__main__":
    unittest.main()
