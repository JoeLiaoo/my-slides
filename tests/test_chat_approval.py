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

HEADINGS = (
    "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
    "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
    "### 布局意图\nLayout.\n### 图标需求\n无\n"
)


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
            spec = (
                f"单元 ID：{unit.id}\n页面角色：{unit.role}\n\n"
                f"## Slide 1 — 其一\n{HEADINGS}\n## Slide 2 — 其二\n{HEADINGS}\n"
            )
            if unit.role == "cover":
                spec = f"单元 ID：{unit.id}\n页面角色：cover\n\n## Slide 1 — 封面\n{HEADINGS}\n"
            unit_paths(self.base, unit.id).report.write_text(report, encoding="utf-8")
            unit_paths(self.base, unit.id).spec.write_text(spec, encoding="utf-8")

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

    def test_spec_review_names_the_changed_page_and_one_edit_stays_local(self):
        self.approve_chapter()
        report_packet = self.review_json(chapter="行业分析")
        self.confirm_chat("report", report_packet["phrase"], chapter="行业分析")
        self.approve_chapter("spec")
        first = self.review_json("spec", chapter="行业分析")
        self.assertIn("没有可对比", first["units"][0]["changes"]["summary"])
        self.confirm_chat("spec", first["phrase"], reply="两节 Spec 都批准", chapter="行业分析")
        spec = unit_paths(self.base, "demand").spec
        spec.write_text(spec.read_text(encoding="utf-8").replace("## Slide 2 — 其二", "## Slide 2 — 调整后"), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approve.run(argparse.Namespace(
                project=str(self.root), kind="spec", units=["demand"], changed=False,
                all_units=False, chapter=None, json=True,
            )), 0)
        second = self.review_json("spec", unit="demand")
        self.assertIn("第 2 页：修改", second["units"][0]["changes"]["summary"])
        self.confirm_chat("spec", second["phrase"], reply="第二页可以，批准", unit="demand")
        spec.write_text(spec.read_text(encoding="utf-8").replace("Conclusion.", "Conclusion revised."), encoding="utf-8")
        demand = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
        other = refresh_unit_currency(self.base, self.units[2], project_root=self.root)
        self.assertFalse(demand["spec"]["current"])
        self.assertTrue(other["spec"]["current"])

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


if __name__ == "__main__":
    unittest.main()
