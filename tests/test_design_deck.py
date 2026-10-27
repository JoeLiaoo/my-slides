"""Design+Slides deck: units ↔ pages mapping, sync, host publishing, checks, and next steps."""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_slides.cli import build_parser
from my_slides.commands import next_step
from my_slides.commands.init import init_project
from my_slides.commands.prepare import prepare
from my_slides.commands.slides import run as slides_run
from my_slides.delivery import export_delivery
from my_slides.design_deck import deck_dir, page_unit, plan_order, publish_deck_files, sync_deck
from my_slides.design_engine import design_status, run_agent
from my_slides.design_workflow import check_deck, check_status, prepare_design_handoff
from my_slides.project import read_config
from my_slides.unit_workflow import approve_unit_report
from my_slides.units import Unit, unit_paths, write_units_manifest

REPORTS = {
    "cover": "# 封面\n\n合成项目：用于验证 Design+Slides 写页路径的示例公司。",
    "market": "# 市场空间\n\n合成数据：目标市场 2025 年规模 120 亿元，年增速约 18%。",
    "team": "# 团队\n\n创始团队三人，均有十年以上行业经验；CTO 曾主导两款产品。",
}
CHECK_PASSED = (0, {"ok": True, "code": "check_passed", "errors": 0, "warnings": 0})


class DesignFixture(unittest.TestCase):
    """一个只有三个单元的合成项目；宿主默认不在线，避免碰到本机正在跑的 5173。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.cfg = read_config(self.base / "project.yaml")
        chapters = self.cfg["chapters"]
        self.units = [
            Unit("cover", chapters[0], "cover"),
            Unit("market", chapters[0], "content", "市场空间"),
            Unit("team", chapters[1], "content", "团队"),
        ]
        write_units_manifest(self.base, self.units)
        for unit in self.units:
            path = unit_paths(self.base, unit.id).report
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(REPORTS[unit.id], encoding="utf-8")
        offline = patch("my_slides.design_deck.host_reachable", return_value=False)
        offline.start()
        self.addCleanup(offline.stop)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def approve(self, *unit_ids: str) -> None:
        for unit in self.units:
            if unit.id in unit_ids:
                approve_unit_report(self.base, unit, when="2026-10-27T18:00:00+08:00",
                                    approved_by="Fixture", approved_account="fixture", project_root=self.root)

    def deck_json(self) -> dict:
        return json.loads((deck_dir(self.base) / "deck.json").read_text(encoding="utf-8"))

    def write_page(self, page: str, body: str) -> None:
        (deck_dir(self.base) / "slides" / f"{page}.html").write_text(
            f'<section id="{page}" style="padding:128px">{body}</section>\n', encoding="utf-8")


class PageMappingTests(unittest.TestCase):
    def test_page_ids_map_to_units_without_prefix_collisions(self) -> None:
        units = {"market", "market-size"}
        self.assertEqual(page_unit("market", units), "market")
        self.assertEqual(page_unit("market_2", units), "market")
        self.assertEqual(page_unit("market-size", units), "market-size")
        self.assertEqual(page_unit("market-size_chart", units), "market-size")
        self.assertIsNone(page_unit("agenda", units))
        self.assertIsNone(page_unit("old_2", units))

    def test_order_follows_units_and_keeps_free_pages_beside_neighbour(self) -> None:
        existing = {"cover", "agenda", "team", "market", "market_2", "market_10"}
        order = plan_order(["cover", "agenda", "team", "market"], ["cover", "market", "team"], existing)
        self.assertEqual(order, ["cover", "agenda", "market", "market_2", "market_10", "team"])

    def test_order_drops_missing_files_and_duplicates(self) -> None:
        order = plan_order(["cover", "gone", "cover"], ["cover"], {"cover"})
        self.assertEqual(order, ["cover"])


class SyncDeckTests(DesignFixture):
    def test_sync_refuses_units_without_current_report_approval(self) -> None:
        self.approve("cover")
        with self.assertRaisesRegex(ValueError, "market"):
            sync_deck(self.base, self.cfg, self.units)
        self.assertFalse((deck_dir(self.base) / "deck.json").exists())

    def test_sync_creates_deck_placeholders_and_sections(self) -> None:
        self.approve("cover", "market", "team")
        result = sync_deck(self.base, self.cfg, self.units)
        self.assertEqual(result["created_pages"], ["cover", "market", "team"])
        self.assertEqual(result["written_via"], "disk")
        deck = self.deck_json()
        self.assertEqual(deck["order"], ["cover", "market", "team"])
        self.assertEqual(deck["cover"], "cover")
        chapters = self.cfg["chapters"]
        self.assertEqual(deck["sections"][chapters[0]]["start"], "cover")
        self.assertEqual(deck["sections"][chapters[1]]["start"], "team")
        page = (deck_dir(self.base) / "slides" / "market.html").read_text(encoding="utf-8")
        self.assertTrue(page.startswith('<section id="market"'))
        self.assertIn("市场空间", page)

    def test_sync_never_rewrites_hand_edited_pages_and_is_idempotent(self) -> None:
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        slides = deck_dir(self.base) / "slides"
        edited = '<section id="market" style="background:#fff">人工修改</section>\n'
        (slides / "market.html").write_text(edited, encoding="utf-8")
        (slides / "market_2.html").write_text('<section id="market_2"></section>\n', encoding="utf-8")
        deck = self.deck_json()
        deck["faces"] = {"x": {"family": "X"}}
        deck["title"] = "人工标题"
        (deck_dir(self.base) / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        first = sync_deck(self.base, self.cfg, self.units)
        second = sync_deck(self.base, self.cfg, self.units)
        self.assertEqual((slides / "market.html").read_text(encoding="utf-8"), edited)
        self.assertEqual(first["created_pages"], [])
        self.assertEqual(self.deck_json()["order"], ["cover", "market", "market_2", "team"])
        self.assertEqual(self.deck_json()["faces"], {"x": {"family": "X"}})
        self.assertEqual(self.deck_json()["title"], "人工标题")
        self.assertTrue(first["deck_changed"])
        self.assertFalse(second["deck_changed"])
        self.assertEqual(second["written_via"], "none")

    def test_sync_only_adds_placeholders_for_selected_units(self) -> None:
        self.approve("market")
        result = sync_deck(self.base, self.cfg, [self.units[1]])
        self.assertEqual(result["order"], ["market"])
        self.assertEqual(result["units_without_pages"], ["cover", "team"])

    def test_dry_run_reports_without_writing(self) -> None:
        self.approve("cover", "market", "team")
        result = sync_deck(self.base, self.cfg, self.units, write=False)
        self.assertTrue(result["deck_changed"])
        self.assertFalse(deck_dir(self.base).exists())


class HostPublishTests(DesignFixture):
    def setUp(self) -> None:
        super().setUp()
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        self.slides = deck_dir(self.base) / "slides"

    def test_running_host_receives_batch_with_disk_baselines(self) -> None:
        old = (self.slides / "market.html").read_bytes()
        seen: dict = {}

        def fake_apply(command, projects_root, **kwargs):
            seen["command"] = command
            seen["batch"] = json.loads(Path(command[command.index("--batch") + 1]).read_text(encoding="utf-8"))
            return 0, {"ok": True, "code": "applied"}

        with patch("my_slides.design_deck.host_reachable", return_value=True), \
             patch("my_slides.design_deck.run_agent", side_effect=fake_apply):
            via = publish_deck_files(self.base, {"slides/market.html": "<section id=\"market\">新</section>\n",
                                                 "slides/extra.html": "<section id=\"extra\"></section>\n",
                                                 "slides/gone.html": None})
        self.assertEqual(via, "host")
        self.assertEqual(seen["command"][:2], ["apply", "deck"])
        files = seen["batch"]["files"]
        self.assertEqual(set(files), {"project/slides/market.html", "project/slides/extra.html"})
        self.assertEqual(files["project/slides/market.html"]["ifMatch"], hashlib.sha256(old).hexdigest())
        self.assertIsNone(files["project/slides/extra.html"]["ifMatch"])
        self.assertEqual(base64.b64decode(files["project/slides/market.html"]["base64"]).decode("utf-8"),
                         "<section id=\"market\">新</section>\n")
        # The host owns the write: nothing touched the disk directly.
        self.assertEqual((self.slides / "market.html").read_bytes(), old)

    def test_conflict_is_reported_and_nothing_is_written(self) -> None:
        conflict = (1, {"ok": False, "code": "conflict", "paths": [{"path": "project/slides/market.html"}]})
        with patch("my_slides.design_deck.host_reachable", return_value=True), \
             patch("my_slides.design_deck.run_agent", return_value=conflict):
            with self.assertRaisesRegex(ValueError, "slides/market.html"):
                publish_deck_files(self.base, {"slides/market.html": "x"})
        self.assertIn("市场空间", (self.slides / "market.html").read_text(encoding="utf-8"))

    def test_host_serving_another_project_falls_back_to_disk(self) -> None:
        unavailable = (2, {"ok": False, "code": "host_unavailable", "message": "projects_root_mismatch"})
        with patch("my_slides.design_deck.host_reachable", return_value=True), \
             patch("my_slides.design_deck.run_agent", return_value=unavailable):
            via = publish_deck_files(self.base, {"slides/market.html": "<section id=\"market\">盘</section>\n"})
        self.assertEqual(via, "disk")
        self.assertIn("盘", (self.slides / "market.html").read_text(encoding="utf-8"))


class CheckStateTests(DesignFixture):
    def test_check_result_is_recorded_and_goes_stale_when_a_page_changes(self) -> None:
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        self.assertFalse(check_status(self.base)["checked"])
        with patch("my_slides.design_workflow.run_agent", return_value=CHECK_PASSED):
            result = check_deck(self.base, self.cfg, strict=True, render=False)
        self.assertTrue(result["valid"])
        self.assertTrue(check_status(self.base)["current"])
        self.write_page("market", "改过")
        status = check_status(self.base)
        self.assertTrue(status["checked"])
        self.assertFalse(status["current"])

    def test_failed_engine_check_is_not_current(self) -> None:
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        failed = (1, {"ok": False, "code": "check_failed", "errors": 1, "warnings": 0})
        with patch("my_slides.design_workflow.run_agent", return_value=failed):
            result = check_deck(self.base, self.cfg, strict=False, render=False)
        self.assertFalse(result["valid"])
        self.assertFalse(check_status(self.base)["current"])


class DesignCommandTests(DesignFixture):
    def test_prepare_slides_writes_design_handoff_after_report_approval(self) -> None:
        with self.assertRaisesRegex(ValueError, "market"):
            prepare_design_handoff(self.base, self.root, [self.units[1]])
        self.approve("market")
        args = argparse.Namespace(project=str(self.root), kind="slides", json=True, question=None,
                                  units=["market"], changed=False, all_units=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare(args), 0)
        text = (self.base / "work" / "slides" / "market.md").read_text(encoding="utf-8")
        self.assertIn("slides/market.html", text)
        self.assertIn("slides skill", text)
        self.assertIn("research/numbers.md", text)
        self.assertIn("my-slides slides build --unit market", text)

    def test_retired_spec_and_browser_commands_are_rejected(self) -> None:
        for argv in (["prepare", "spec"], ["approve", "spec"], ["renderer", "doctor"], ["browser", "doctor"],
                     ["slides", "visual-review"], ["slides", "check", "--screenshots"], ["init", "--presentation", "design"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                build_parser().parse_args(argv)

    def test_slides_build_routes_to_deck_sync(self) -> None:
        self.approve("cover", "market", "team")
        args = argparse.Namespace(project=str(self.root), slides_command="build", json=True,
                                  units=None, changed=False, all_units=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(slides_run(args), 0)
        self.assertEqual(self.deck_json()["order"], ["cover", "market", "team"])


class NextStepFlowTests(DesignFixture):
    """报告批准之后，next 依次指向写页 → 同步 → 检查 → 用户审阅 → 导出。"""

    def next_step(self) -> dict:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(next_step.run(argparse.Namespace(project=str(self.root), json=True, all=False)), 0)
        return json.loads(out.getvalue())["next"]

    def test_flow_after_report_approval(self) -> None:
        self.approve("cover", "market", "team")
        (self.base / "reports" / "report.md").unlink(missing_ok=True)
        self.assertIn("my-slides assemble", self.next_step()["command"])
        from my_slides.units import assemble_report
        assemble_report(self.base, self.units, write=True)
        self.assertIn("prepare evidence-research", self.next_step()["command"])
        (self.base / "research").mkdir(exist_ok=True)
        (self.base / "research" / "numbers.md").write_text(
            "| 编号 | 指标/数据集 | 数值/序列 | 单位 | 期间 | 来源 | URL | 口径/估计 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| N-001 | 市场规模 | 120 | 亿元 | 2025 | 示例机构《市场报告》（2025-06） | https://example.com/r | 无 |\n",
            encoding="utf-8",
        )
        step = self.next_step()
        self.assertIn("prepare slides --unit cover", step["command"])

        sync_deck(self.base, self.cfg, self.units)
        step = self.next_step()
        self.assertIn("prepare slides --unit cover", step["command"])
        self.assertIn("占位", step["reason"])

        self.write_page("cover", "<h1>示例公司</h1>")
        self.write_page("market", "<h2>市场空间 120 亿元</h2>")
        self.write_page("team", "<h2>团队</h2>")
        self.assertIn("slides check --all", self.next_step()["command"])

        (deck_dir(self.base) / "slides" / "team_2.html").write_text('<section id="team_2"></section>', encoding="utf-8")
        self.assertIn("slides build --all", self.next_step()["command"])
        sync_deck(self.base, self.cfg, [])

        with patch("my_slides.design_workflow.run_agent", return_value=CHECK_PASSED):
            check_deck(self.base, self.cfg, strict=False, render=False)
        review = self.next_step()
        self.assertEqual(review["actor"], "human")
        self.assertIn("slides open", review["command"])
        self.assertIn("export", review["reason"])

        def fake_export(command, projects_root, **kwargs):
            Path(command[command.index("--out") + 1]).write_text("<html></html>", encoding="utf-8")
            return 0, {"ok": True, "code": "exported"}

        with patch("my_slides.delivery.run_agent", side_effect=fake_export):
            export_delivery(self.base, self.cfg, project_root=self.root)
        done = self.next_step()
        self.assertIsNone(done["command"])
        self.write_page("market", "<h2>市场空间 125 亿元</h2>")
        self.assertIn("slides check --all", self.next_step()["command"])


@unittest.skipUnless(os.environ.get("MY_SLIDES_DESIGN_ROOT") and design_status()["ready"],
                     "需要 MY_SLIDES_DESIGN_ROOT 指向已安装并构建的 design-and-slides")
class DesignEngineIntegrationTests(DesignFixture):
    def test_synced_placeholder_deck_passes_design_check(self) -> None:
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        result = check_deck(self.base, self.cfg, strict=True, render=False)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["structure"]["code"], "check_passed")

    def test_missing_unit_page_fails_check(self) -> None:
        self.approve("cover", "market", "team")
        sync_deck(self.base, self.cfg, self.units)
        (deck_dir(self.base) / "slides" / "team.html").unlink()
        sync_deck(self.base, self.cfg, self.units[:2])
        result = check_deck(self.base, self.cfg, strict=False, render=False)
        self.assertFalse(result["valid"])
        self.assertTrue(any("team" in error for error in result["errors"]))

    def test_skill_examples_pass_strict_design_check(self) -> None:
        # skill 里的示例页面会被 Agent 直接复制，必须是严格检查下零警告的 Design 页面。
        examples = Path(__file__).resolve().parents[1] / "skills" / "my-slides-workflow" / "examples"
        pages = sorted(examples.glob("*/*/page.html"))
        self.assertTrue(pages)
        deck = self.root / "examples-deck" / "ex"
        (deck / "slides").mkdir(parents=True)
        order = []
        for page in pages:
            text = page.read_text(encoding="utf-8")
            page_id = text.split('<section id="', 1)[1].split('"', 1)[0]
            (deck / "slides" / f"{page_id}.html").write_text(text, encoding="utf-8")
            order.append(page_id)
        (deck / "deck.json").write_text(json.dumps({
            "v": 4, "lists": "css", "title": "examples", "order": order, "cover": order[0],
            "sections": {}, "faces": {}, "designSystems": []}), encoding="utf-8")
        code, result = run_agent(["check", "ex", "--strict"], deck.parent)
        self.assertEqual(code, 0, result.get("diagnostics"))


if __name__ == "__main__":
    unittest.main()
