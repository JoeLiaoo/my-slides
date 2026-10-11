"""Reject, withdraw, and revoke flows for v2 approvals."""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides.commands import approve, confirm, next_step, reject, revoke, status, withdraw
from my_slides.commands.init import init_project
from my_slides.state import read_unit_state, refresh_unit_currency
from my_slides.units import Unit, unit_paths, write_units_manifest

HEADINGS = (
    "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
    "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
    "### 布局意图\nLayout.\n### 图标需求\n无\n"
)


class ApprovalDecisionsTests(unittest.TestCase):
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

    def request(self, unit_id, kind="report"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = approve.run(argparse.Namespace(
                project=str(self.root), kind=kind, units=[unit_id], changed=False,
                all_units=False, chapter=None, json=True,
            ))
        self.assertEqual(code, 0, out.getvalue())

    def review_phrase(self, kind="report", unit=None, chapter=None, *, which="approve"):
        from my_slides.commands import review
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = review.run(argparse.Namespace(
                project=str(self.root), kind=kind, json=True, unit=unit, chapter=chapter,
            ))
        self.assertEqual(code, 0, out.getvalue())
        packet = json.loads(out.getvalue())
        key = "phrase" if which == "approve" else "reject_phrase"
        return packet[key]

    def confirm_chat(self, kind, phrase, reply="批准"):
        args = argparse.Namespace(
            project=str(self.root), kind=kind, via="chat", phrase=phrase,
            user_reply=reply, reviewer=None, unit=self.units[0].id, chapter=None,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            return confirm.run(args)

    def reject_chat(self, kind, phrase, reason, reply="驳回", unit=None, chapter=None):
        if unit is None and chapter is None:
            unit = self.units[0].id
        args = argparse.Namespace(
            project=str(self.root), kind=kind, via="chat", phrase=phrase,
            user_reply=reply, reviewer=None, reason=reason,
            unit=unit, chapter=chapter,
            json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = reject.run(args)
        self.assertEqual(code, 0, out.getvalue())
        return json.loads(out.getvalue())

    def status_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = status.run(argparse.Namespace(project=str(self.root), units=None, json=True))
        self.assertEqual(code, 0, out.getvalue())
        return json.loads(out.getvalue())

    def next_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = next_step.run(argparse.Namespace(project=str(self.root), json=True))
        self.assertEqual(code, 0, out.getvalue())
        return json.loads(out.getvalue())["next"]

    # -- reject --------------------------------------------------------------

    def test_chat_reject_records_decision_and_suggests_re_approve(self):
        self.request("cover")
        phrase = self.review_phrase(unit="cover", which="reject")
        result = self.reject_chat("report", phrase, reason="结论与证据不一致", reply="先不批准")
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["channel"], "chat")
        state = read_unit_state(self.base, "cover")["report"]
        self.assertFalse(state["current"])
        self.assertEqual(state["latest_decision"], "rejected")
        self.assertEqual(state["latest_rejection"]["reason"], "结论与证据不一致")
        self.assertEqual(state["latest_rejection"]["channel"], "chat")
        self.assertEqual(state["latest_rejection"]["rejected_by"], "张三")
        self.assertIsNone(state["pending_approval"])
        # history has the rejection entry.
        decisions = [item["decision"] for item in state["decision_history"]]
        self.assertIn("rejected", decisions)
        # status surfaces rejection with reason per unit.
        report_status = self.status_json()["approvals"]["report"]
        self.assertIn("cover", report_status["rejected_units"])
        self.assertEqual(report_status["rejections"]["cover"]["reason"], "结论与证据不一致")
        # next asks the agent to revise and includes the rejection reason.
        step = self.next_json()
        self.assertIn("approve report --unit cover", step["command"])
        self.assertEqual(step["actor"], "agent")
        self.assertIn("结论与证据不一致", step["reason"])

    def test_review_exposes_both_approve_and_reject_phrases(self):
        self.request("cover")
        from my_slides.commands import review
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(review.run(argparse.Namespace(
                project=str(self.root), kind="report", json=True, unit="cover", chapter=None,
            )), 0)
        packet = json.loads(out.getvalue())
        self.assertTrue(packet["phrase"].startswith("APPROVE REPORT cover "))
        self.assertTrue(packet["reject_phrase"].startswith("REJECT REPORT cover "))
        self.assertNotEqual(packet["phrase"], packet["reject_phrase"])

    def test_chat_reject_rejects_approve_phrase(self):
        self.request("cover")
        approve_phrase = self.review_phrase(unit="cover", which="approve")
        with self.assertRaisesRegex(ValueError, "短语"):
            self.reject_chat("report", approve_phrase, reason="用了错的短语", reply="驳回")
        # State stays pending; no rejection was recorded.
        state = read_unit_state(self.base, "cover")["report"]
        self.assertIsNotNone(state["pending_approval"])
        self.assertNotEqual(state.get("latest_decision"), "rejected")

    def test_chat_confirm_rejects_reject_phrase(self):
        self.request("cover")
        reject_phrase = self.review_phrase(unit="cover", which="reject")
        with self.assertRaisesRegex(ValueError, "短语"):
            self.confirm_chat("report", reject_phrase, reply="批准")
        state = read_unit_state(self.base, "cover")["report"]
        self.assertIsNotNone(state["pending_approval"])
        self.assertFalse(state["current"])

    def test_reject_without_reason_errors(self):
        with self.assertRaisesRegex(ValueError, "驳回原因"):
            reject.run(argparse.Namespace(
                project=str(self.root), kind="report", unit="cover",
                via=None, phrase=None, user_reply=None, reviewer=None,
                reason="", chapter=None, json=True,
            ))

    def test_terminal_mode_rejects_chat_reject(self):
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "approval_mode: terminal\n", encoding="utf-8")
        self.request("cover")
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.reject_chat("report", "irrelevant", reason="原因", unit="cover")

    def test_terminal_reject_requires_interactive_tty(self):
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "approval_mode: terminal\n", encoding="utf-8")
        self.request("cover")
        with patch("my_slides.commands.reject.sys") as terminal:
            terminal.stdin.isatty.return_value = False
            terminal.stdout.isatty.return_value = True
            with self.assertRaisesRegex(ValueError, "交互终端"):
                reject.run(argparse.Namespace(
                    project=str(self.root), kind="report", unit="cover",
                    via=None, phrase=None, user_reply=None, reviewer=None,
                    reason="原因", chapter=None, json=True,
                ))

    def test_terminal_reject_happy_path(self):
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "approval_mode: terminal\n", encoding="utf-8")
        self.request("cover")
        with patch("my_slides.commands.reject.sys") as terminal, \
             patch("my_slides.commands.reject.getpass.getuser", return_value="review-account"), \
             patch("builtins.input", side_effect=["Human Reviewer", ""]):
            terminal.stdin.isatty.return_value = True
            terminal.stdout.isatty.return_value = True
            with self.assertRaisesRegex(ValueError, "确认文字"):
                reject.run(argparse.Namespace(
                    project=str(self.root), kind="report", unit="cover",
                    via=None, phrase=None, user_reply=None, reviewer=None,
                    reason="结论依据需要修订", chapter=None, json=False,
                ))
        # Re-request and approve-like flow with the right reject phrase.
        self.request("cover")
        request = read_unit_state(self.base, "cover")["report"]["pending_approval"]
        digest = request["content_sha256"][:12]
        with patch("my_slides.commands.reject.sys") as terminal, \
             patch("my_slides.commands.reject.getpass.getuser", return_value="review-account"), \
             patch("builtins.input", side_effect=["Human Reviewer", f"REJECT REPORT cover {digest}"]):
            terminal.stdin.isatty.return_value = True
            terminal.stdout.isatty.return_value = True
            self.assertEqual(reject.run(argparse.Namespace(
                project=str(self.root), kind="report", unit="cover",
                via=None, phrase=None, user_reply=None, reviewer=None,
                reason="结论依据需要修订", chapter=None, json=False,
            )), 0)
        state = read_unit_state(self.base, "cover")["report"]
        self.assertFalse(state["current"])
        self.assertEqual(state["latest_decision"], "rejected")
        self.assertEqual(state["latest_rejection"]["channel"], "terminal")
        self.assertEqual(state["latest_rejection"]["rejected_by"], "Human Reviewer")
        self.assertEqual(state["latest_rejection"]["rejected_account"], "review-account")
        self.assertEqual(state["latest_rejection"]["reason"], "结论依据需要修订")

    # -- withdraw ------------------------------------------------------------

    def test_withdraw_clears_pending_without_user_gate(self):
        self.request("cover")
        args = argparse.Namespace(
            project=str(self.root), kind="report", unit="cover", json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(withdraw.run(args), 0)
        state = read_unit_state(self.base, "cover")["report"]
        self.assertIsNone(state["pending_approval"])
        self.assertFalse(state["pending_current"])
        # No decision record — withdrawal is not a user choice.
        self.assertNotEqual(state.get("latest_decision"), "rejected")
        self.assertFalse(state["current"])
        history = [item["decision"] for item in state["decision_history"]]
        self.assertIn("withdrawn", history)

    def test_withdraw_without_pending_errors(self):
        args = argparse.Namespace(
            project=str(self.root), kind="report", unit="cover", json=True,
        )
        with self.assertRaisesRegex(ValueError, "没有待审"):
            withdraw.run(args)

    def test_re_approve_after_rejection_clears_rejection_state_but_keeps_history(self):
        self.request("cover")
        phrase = self.review_phrase(unit="cover", which="reject")
        self.reject_chat("report", phrase, reason="首次结论需要修订", reply="先不批")
        # After rejection, approve again and confirm. (Phrase stays the same
        # because the report content is unchanged.)
        self.request("cover")
        self.confirm_chat("report", self.review_phrase(unit="cover"), reply="修订后批准")
        state = read_unit_state(self.base, "cover")["report"]
        self.assertTrue(state["current"])
        self.assertEqual(state["latest_decision"], "approved")
        self.assertNotEqual(state["latest_rejection"]["reason"], "")
        # Rejection is still in history.
        history = [item["decision"] for item in state["decision_history"]]
        self.assertIn("rejected", history)
        self.assertIn("approved", history)

    # -- revoke --------------------------------------------------------------

    def test_revoke_report_invalidates_spec_html_and_checks(self):
        # Approve report and spec first.
        self.request("cover")
        report_phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", report_phrase)
        self.request("cover", kind="spec")
        spec_phrase = self.review_phrase(unit="cover", kind="spec")
        self.confirm_chat("spec", spec_phrase, reply="Spec 批准")
        self.assertTrue(read_unit_state(self.base, "cover")["spec"]["current"])
        # Build HTML so we can confirm revoke marks it invalid.
        paths = unit_paths(self.base, "cover")
        paths.page.parent.mkdir(parents=True, exist_ok=True)
        paths.page.write_text(
            '<section class="slide" data-unit-id="cover" data-page-role="cover"></section>',
            encoding="utf-8",
        )
        # Mark html/check current so we can confirm the revoke resets them.
        state = read_unit_state(self.base, "cover")
        from my_slides.dependencies import fingerprint_file
        state["html"]["build_sha256"] = fingerprint_file(paths.page)
        state["html"]["spec_sha256"] = state["spec"]["approved_sha256"]
        from my_slides.theme import shell_fingerprint
        state["html"]["shell_fingerprint"] = shell_fingerprint()
        state["html"]["current"] = True
        state["check"]["result"] = "pass"
        from my_slides.state import check_input_fingerprint, write_unit_state
        state["check"]["input_fingerprint"] = check_input_fingerprint(
            state["html"]["build_sha256"], state["spec"]["approved_sha256"], deck_sha=None,
        )
        state["check"]["current"] = True
        write_unit_state(self.base, "cover", state)
        state = refresh_unit_currency(self.base, self.units[0], project_root=self.root)
        self.assertTrue(state["html"]["current"])
        # Revoke the report approval via chat using the current binding.
        from my_slides.approval_review import bindings_digest, revoke_binding, revoke_phrase
        from my_slides.state import refresh_unit_currency as _refresh
        state = _refresh(self.base, self.units[0], project_root=self.root)
        binding = revoke_binding(self.units[0], "report", state)
        digest = bindings_digest([binding], chapter_scope=False)
        phrase = revoke_phrase("report", self.units[0].id, digest)
        args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase=phrase, user_reply="撤回报告批准", reviewer=None,
            unit="cover", chapter=None, reason="结论口径变了", json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(revoke.run(args), 0)
        state = read_unit_state(self.base, "cover")
        self.assertFalse(state["report"]["current"])
        self.assertIsNone(state["report"]["approved_sha256"])
        self.assertEqual(state["report"]["latest_decision"], "rejected")
        self.assertEqual(state["report"]["latest_rejection"]["reason"], "结论口径变了")
        self.assertFalse(state["spec"]["current"])
        self.assertIsNone(state["spec"]["approved_sha256"])
        self.assertFalse(state["html"]["current"])
        self.assertFalse(state["check"]["current"])
        # Approved copy is preserved in archive.
        archive_dir = self.base / ".state" / "approved" / "report" / "cover"
        self.assertTrue(any(archive_dir.glob("*.md")))
        spec_archive = self.base / ".state" / "approved" / "spec" / "cover"
        self.assertTrue(any(spec_archive.glob("*.md")))

    # -- reject -> restore -> next does not loop on the rejected reason -----

    def test_next_after_restore_matches_approved_does_not_recommend_re_approve(self):
        # Approve report v1.
        self.request("cover")
        approve_phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", approve_phrase, reply="首次批准")
        # Edit to v2 and submit a pending request.
        report_file = unit_paths(self.base, "cover").report
        report_file.write_text(report_file.read_text(encoding="utf-8") + "\nv2 补充。\n", encoding="utf-8")
        self.request("cover")
        # Reject v2 via chat with the REJECT phrase.
        reject_phrase = self.review_phrase(unit="cover", which="reject")
        self.reject_chat("report", reject_phrase, reason="需要重新核实数据", reply="驳回")
        # Restore the file content to v1 (matches approved_sha256).
        report_file.write_text(unit_paths(self.base, "cover").report.read_text(encoding="utf-8").split("\nv2 补充。\n")[0], encoding="utf-8")
        state = refresh_unit_currency(self.base, self.units[0], project_root=self.root)
        self.assertTrue(state["report"]["current"])
        self.assertEqual(state["report"]["latest_decision"], "rejected")
        # status sees the unit as approved and the rejection is no longer
        # considered actionable (report_current=true).
        report_status = self.status_json()["approvals"]["report"]
        self.assertIn("cover", report_status["approved_units"])
        self.assertNotIn("cover", report_status["rejected_units"])
        # next must NOT recommend ``approve report --unit cover`` again.
        step = self.next_json()
        self.assertNotIn("approve report --unit cover", step["command"] or "")
        # The rejection record is preserved in history.
        state = read_unit_state(self.base, "cover")["report"]
        self.assertEqual(state["latest_rejection"]["reason"], "需要重新核实数据")
        history = [item["decision"] for item in state["decision_history"]]
        self.assertIn("rejected", history)

    def test_revoke_requires_existing_approval(self):
        args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase="REVOKE REPORT cover 000000000000", user_reply="撤回", reviewer=None,
            unit="cover", chapter=None, reason=None, json=True,
        )
        with self.assertRaisesRegex(ValueError, "没有用户批准"):
            revoke.run(args)

    def test_terminal_revoke_requires_tty(self):
        config = self.base / "project.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "approval_mode: terminal\n", encoding="utf-8")
        # Approve via terminal flow first.
        self.request("cover")
        with patch("my_slides.commands.confirm.sys") as terminal, \
             patch("my_slides.commands.confirm.getpass.getuser", return_value="review-account"), \
             patch("builtins.input", side_effect=["Human Reviewer", f"APPROVE REPORT cover {read_unit_state(self.base, 'cover')['report']['pending_approval']['content_sha256'][:12]}"]):
            terminal.stdin.isatty.return_value = True
            terminal.stdout.isatty.return_value = True
            self.assertEqual(confirm.run(argparse.Namespace(
                project=str(self.root), kind="report", unit="cover",
            )), 0)
        # Now revoke in terminal mode without TTY.
        with patch("my_slides.commands.revoke.sys") as terminal:
            terminal.stdin.isatty.return_value = False
            terminal.stdout.isatty.return_value = True
            with self.assertRaisesRegex(ValueError, "交互终端"):
                revoke.run(argparse.Namespace(
                    project=str(self.root), kind="report", unit="cover",
                    via=None, phrase=None, user_reply=None, reviewer=None,
                    reason="口径调整", chapter=None, json=False,
                ))

    def test_revoke_chat_phrase_mismatch(self):
        self.request("cover")
        phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", phrase, reply="批准")
        args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase="REVOKE REPORT cover 000000000000", user_reply="撤回", reviewer=None,
            unit="cover", chapter=None, reason=None, json=True,
        )
        with self.assertRaisesRegex(ValueError, "短语"):
            revoke.run(args)
        self.assertTrue(read_unit_state(self.base, "cover")["report"]["current"])

    def test_revoke_chat_works_after_content_diverges_from_approved(self):
        # Approve v1 so approved_sha256 is set.
        self.request("cover")
        approve_phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", approve_phrase, reply="首次批准")
        # Diverging the file from the approved version (without approving a new
        # one) makes ``report_current`` false while ``approved_sha256`` stays set.
        report_file = unit_paths(self.base, "cover").report
        report_file.write_text(report_file.read_text(encoding="utf-8") + "\n手动调整，未提交审批。\n", encoding="utf-8")
        state = refresh_unit_currency(self.base, self.units[0], project_root=self.root)
        self.assertIsNotNone(state["report"]["approved_sha256"])
        self.assertFalse(state["report"]["current"])
        # First chat revoke run should print the REVOKE phrase (no recording).
        preview_args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase="", user_reply="", reviewer=None,
            unit="cover", chapter=None, reason="过期批准需撤回", json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(revoke.run(preview_args), 0)
        preview = json.loads(out.getvalue())
        self.assertEqual(preview["decision"], "revoke-preview")
        self.assertTrue(preview["phrase"].startswith("REVOKE REPORT cover "))
        # Second chat revoke run with the phrase must succeed even though
        # ``report_current`` is False — the user is withdrawing a stale one.
        final_args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase=preview["phrase"], user_reply="撤回过期批准", reviewer=None,
            unit="cover", chapter=None, reason="过期批准需撤回", json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(revoke.run(final_args), 0)
        state = read_unit_state(self.base, "cover")["report"]
        self.assertIsNone(state["approved_sha256"])
        self.assertEqual(state["latest_decision"], "rejected")
        self.assertEqual(state["latest_rejection"]["reason"], "过期批准需撤回")

    # -- re-submission after rejection ---------------------------------------

    def test_re_submit_after_rejection_recommends_review_and_marks_pending(self):
        self.request("cover")
        phrase = self.review_phrase(unit="cover", which="reject")
        self.reject_chat("report", phrase, reason="结论需要修订", reply="先不批")
        # After the rejection, re-submit by running approve again.
        self.request("cover")
        # status should list this unit as pending, not rejected.
        report_status = self.status_json()["approvals"]["report"]
        self.assertIn("cover", report_status["pending_units"])
        self.assertNotIn("cover", report_status["rejected_units"])
        # next should recommend review (chat mode), not approve.
        step = self.next_json()
        self.assertEqual(step["actor"], "human")
        self.assertIn("review report --unit cover", step["command"])
        self.assertNotIn("approve report --unit cover", step["command"])
        # The rejection reason is still on record in the unit state for traceability.
        state = read_unit_state(self.base, "cover")["report"]
        self.assertEqual(state["latest_rejection"]["reason"], "结论需要修订")
        history = [item["decision"] for item in state["decision_history"]]
        self.assertIn("rejected", history)

    def test_reject_does_not_destroy_existing_approvals(self):
        # Approve report v1 first so the unit has an active approval.
        self.request("cover")
        report_phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", report_phrase, reply="首次批准")
        # Approve a Spec that is bound to the same report version.
        self.request("cover", kind="spec")
        spec_phrase = self.review_phrase(unit="cover", kind="spec")
        self.confirm_chat("spec", spec_phrase, reply="Spec 批准")
        state = read_unit_state(self.base, "cover")
        report_v1_sha = state["report"]["approved_sha256"]
        spec_sha = state["spec"]["approved_sha256"]
        bound_report_sha = state["spec"]["report_sha256"]
        self.assertEqual(report_v1_sha, bound_report_sha)
        self.assertIsNotNone(report_v1_sha)
        self.assertIsNotNone(spec_sha)
        # Edit the report and submit a new request, then revoke-style decline it.
        report_file = unit_paths(self.base, "cover").report
        report_file.write_text(report_file.read_text(encoding="utf-8") + "\n补充一段。\n", encoding="utf-8")
        self.request("cover")
        new_phrase = self.review_phrase(unit="cover", which="reject")
        self.assertNotEqual(new_phrase, report_phrase)
        self.reject_chat("report", new_phrase, reason="补充资料未准备", reply="重写")
        # The previously approved versions survive.
        state = read_unit_state(self.base, "cover")
        self.assertEqual(state["report"]["approved_sha256"], report_v1_sha)
        self.assertEqual(state["spec"]["approved_sha256"], spec_sha)
        self.assertEqual(state["spec"]["report_sha256"], report_v1_sha)
        self.assertIsNone(state["report"]["pending_approval"])
        self.assertEqual(state["report"]["latest_decision"], "rejected")
        # The new content is not yet current because the edit broke binding.
        self.assertFalse(state["report"]["current"])
        # refresh_unit_currency will keep the existing approval fields until a
        # genuine new approval replaces them.

    # -- revoke chat preview phrase -------------------------------------------

    def test_revoke_chat_preview_returns_phrase_without_recording(self):
        self.request("cover")
        phrase = self.review_phrase(unit="cover")
        self.confirm_chat("report", phrase, reply="首次批准")
        before = read_unit_state(self.base, "cover")["report"]
        # Run revoke without --phrase and --user-reply: should print info
        # and return the phrase but record nothing.
        args = argparse.Namespace(
            project=str(self.root), kind="report", via="chat",
            phrase="", user_reply="", reviewer=None,
            unit="cover", chapter=None, reason=None, json=True,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(revoke.run(args), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["decision"], "revoke-preview")
        self.assertTrue(payload["phrase"].startswith("REVOKE REPORT cover "))
        self.assertEqual(payload["units"][0]["approved_sha256"], before["approved_sha256"])
        after = read_unit_state(self.base, "cover")["report"]
        self.assertEqual(after["approved_sha256"], before["approved_sha256"])
        self.assertTrue(after["current"])

    # -- backward compatibility ----------------------------------------------

    def test_legacy_state_file_loads_without_new_fields(self):
        # Simulate a state file written before the rejection fields existed.
        legacy = {
            "unit_id": "cover",
            "report": {
                "approved_sha256": "legacy-sha",
                "approved_at": "2025-01-01T00:00:00",
                "approved_by": "Legacy User",
                "approved_account": "legacy-account",
                "current": True,
            },
            "spec": {"current": False},
            "html": {"current": False},
            "check": {"current": False},
            "reasons": [],
        }
        import json
        (self.base / ".state" / "units" / "cover.json").parent.mkdir(parents=True, exist_ok=True)
        (self.base / ".state" / "units" / "cover.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8",
        )
        state = read_unit_state(self.base, "cover")
        self.assertEqual(state["report"]["latest_decision"], None)
        self.assertIsNone(state["report"]["latest_rejection"])
        self.assertEqual(state["report"]["decision_history"], [])
        # refresh still computes current flags.
        refreshed = refresh_unit_currency(self.base, self.units[0], project_root=self.root)
        self.assertIn("report", refreshed)
        self.assertIn("spec", refreshed)


if __name__ == "__main__":
    unittest.main()