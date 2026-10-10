"""Sections may contain multiple slides; approval stays at section granularity."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from my_slides.assembly import build_units_deck
from my_slides.browser import structural_check_deck
from my_slides.commands.init import init_project
from my_slides.state import refresh_unit_currency
from my_slides.unit_management import retitle_unit
from my_slides.unit_workflow import approve_unit_report, approve_unit_spec, validate_unit_spec
from my_slides.units import Unit, unit_paths, write_units_manifest

TEST_APPROVER = {"approved_by": "Fixture Reviewer", "approved_account": "fixture"}
HEADINGS = (
    "### 目的\nExplain.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
    "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
    "### 布局意图\nLayout.\n### 图标需求\n无\n"
)


def _slide(number: int, title: str, extra: str = "") -> str:
    return f"## Slide {number} — {title}\n{HEADINGS}{extra}"


def _html(unit_id: str, titles: list[str], extras: list[str] | None = None) -> str:
    extras = extras or [""] * len(titles)
    return "\n".join(
        f'<section class="slide" data-page-role="content" data-unit-id="{unit_id}">'
        f"<h1>{title}</h1>{extra}"
        f'<script type="application/json" class="slide-notes">'
        f'{{"title":"{title}","script":"Hi","notes":[]}}</script></section>'
        for title, extra in zip(titles, extras, strict=True)
    )


class MultiPageSectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.chapters = ["投资概要", "行业分析"]
        self.units = [
            Unit(id="cover", chapter="投资概要", role="cover", title="封面"),
            Unit(id="demand", chapter="行业分析", role="content", title="需求分析"),
            Unit(id="competition", chapter="行业分析", role="content", title="竞争分析"),
        ]
        write_units_manifest(self.base, self.units)
        for unit in self.units:
            paths = unit_paths(self.base, unit.id)
            paths.report.write_text(f"# {unit.title}\n\nEnough report text for validation of this section.\n", encoding="utf-8")
            role = unit.role
            paths.spec.write_text(f"单元 ID：{unit.id}\n页面角色：{role}\n\n{_slide(1, unit.title)}\n", encoding="utf-8")
            paths.page.write_text(
                f'<section class="slide" data-page-role="{role}" data-unit-id="{unit.id}"><h1>{unit.title}</h1>'
                f'<script type="application/json" class="slide-notes">{{"title":"{unit.title}","script":"Hi","notes":[]}}</script></section>',
                encoding="utf-8",
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_page_id_spec_still_validates(self):
        unit = self.units[1]
        unit_paths(self.base, unit.id).spec.write_text(
            f"## Slide 1 — 需求分析\n页面 ID：{unit.id}\n页面角色：content\n{HEADINGS}",
            encoding="utf-8",
        )
        self.assertEqual(validate_unit_spec(self.base, unit), [])

    def test_spec_accepts_consecutive_pages_and_rejects_bad_shapes(self):
        unit = self.units[1]
        unit_paths(self.base, unit.id).spec.write_text(
            f"单元 ID：demand\n页面角色：content\n\n{_slide(1, '规模')}\n{_slide(2, '驱动')}\n",
            encoding="utf-8",
        )
        self.assertEqual(validate_unit_spec(self.base, unit), [])

        unit_paths(self.base, unit.id).spec.write_text(
            f"单元 ID：demand\n页面角色：content\n\n{_slide(1, '规模')}\n{_slide(3, '驱动')}\n",
            encoding="utf-8",
        )
        self.assertTrue(any("连续" in error for error in validate_unit_spec(self.base, unit)))

        pages = "\n".join(_slide(number, f"第{number}页") for number in range(1, 10))
        unit_paths(self.base, unit.id).spec.write_text(f"单元 ID：demand\n页面角色：content\n\n{pages}\n", encoding="utf-8")
        self.assertTrue(any("最多" in error for error in validate_unit_spec(self.base, unit)))

        cover = self.units[0]
        unit_paths(self.base, cover.id).spec.write_text(
            f"单元 ID：cover\n页面角色：cover\n\n{_slide(1, '封面')}\n{_slide(2, '第二页')}\n",
            encoding="utf-8",
        )
        self.assertTrue(any("封面" in error for error in validate_unit_spec(self.base, cover)))

    def test_three_pages_assemble_in_order_and_reject_cross_page_charts(self):
        demand = self.units[1]
        titles = ["规模", "驱动", "结论"]
        unit_paths(self.base, demand.id).spec.write_text(
            "单元 ID：demand\n页面角色：content\n\n" + "\n".join(_slide(n, title) for n, title in enumerate(titles, 1)),
            encoding="utf-8",
        )
        unit_paths(self.base, demand.id).page.write_text(_html(demand.id, titles), encoding="utf-8")
        for unit in self.units:
            approve_unit_report(self.base, unit, when="t0", project_root=self.root, **TEST_APPROVER)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root, **TEST_APPROVER)
        cfg = {"project": "Demo", "chapters": self.chapters, "brand_color": "#A6192E"}
        output, errors, _plan = build_units_deck(self.base, cfg, all_units=True, write=True)
        self.assertEqual(errors, [], errors)
        html = output.read_text(encoding="utf-8")
        self.assertIn('data-slide="0"', html)
        self.assertIn('data-unit-id="demand" data-unit-page="1"', html)
        self.assertIn('data-unit-id="demand" data-unit-page="3"', html)
        self.assertIn('data-slide="3"', html)
        structural = structural_check_deck(
            output,
            expected_units=[unit.id for unit in self.units],
            expected_page_counts={"cover": 1, "demand": 3, "competition": 1},
        )
        self.assertTrue(structural["valid"], structural["errors"])

        chart = {"type": "bar", "title": "规模", "categories": ["2024"], "values": [10], "unit": "亿元"}
        spec = unit_paths(self.base, demand.id).spec.read_text(encoding="utf-8")
        spec = spec.replace("### 展示内容\nContent.\n", "### 展示内容\nContent.\n```echarts-spec\n" + json.dumps(chart) + "\n```\n", 1)
        unit_paths(self.base, demand.id).spec.write_text(spec, encoding="utf-8")
        approve_unit_spec(self.base, demand, when="t2", project_root=self.root, **TEST_APPROVER)
        chart_markup = '<script type="application/json" class="mls-echarts-spec">' + json.dumps(chart) + "</script>"
        unit_paths(self.base, demand.id).page.write_text(_html(demand.id, titles, ["", chart_markup, ""]), encoding="utf-8")
        _output, errors, _plan = build_units_deck(self.base, cfg, unit_ids=["demand"], write=True)
        self.assertTrue(any("第 2 页" in error and "完全一致" in error for error in errors), errors)

    def test_layout_edit_keeps_approval_and_spec_edit_is_local(self):
        for unit in self.units:
            approve_unit_report(self.base, unit, when="t0", project_root=self.root, **TEST_APPROVER)
            approve_unit_spec(self.base, unit, when="t1", project_root=self.root, **TEST_APPROVER)
        page = unit_paths(self.base, "demand").page
        page.write_text(page.read_text(encoding="utf-8").replace("<h1>需求分析</h1>", "<h1>需求分析（改版式）</h1>"), encoding="utf-8")
        demand_state = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
        self.assertTrue(demand_state["report"]["current"])
        self.assertTrue(demand_state["spec"]["current"])
        self.assertFalse(demand_state["html"]["current"])

        spec = unit_paths(self.base, "demand").spec
        spec.write_text(spec.read_text(encoding="utf-8").replace("Conclusion.", "Conclusion revised."), encoding="utf-8")
        demand_state = refresh_unit_currency(self.base, self.units[1], project_root=self.root)
        other_state = refresh_unit_currency(self.base, self.units[2], project_root=self.root)
        self.assertFalse(demand_state["spec"]["current"])
        self.assertTrue(other_state["spec"]["current"])
        self.assertTrue(other_state["report"]["current"])

    def test_retitle_keeps_approvals(self):
        unit = self.units[1]
        approve_unit_report(self.base, unit, when="t0", project_root=self.root, **TEST_APPROVER)
        approve_unit_spec(self.base, unit, when="t1", project_root=self.root, **TEST_APPROVER)
        result = retitle_unit(self.base, "demand", "需求规模", self.chapters)
        self.assertTrue(result["approvals_preserved"])
        state = refresh_unit_currency(self.base, Unit(id="demand", chapter="行业分析", role="content", title="需求规模"), project_root=self.root)
        self.assertTrue(state["report"]["current"])
        self.assertTrue(state["spec"]["current"])
        self.assertFalse(state["check"]["current"])

    def test_structural_check_reports_page_count_mismatch(self):
        path = self.base / "slides" / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<meta name="generator" content="my-slides">'
            '<section class="slide" data-unit-id="cover" data-page-role="cover"></section>'
            '<section class="slide" data-unit-id="demand" data-page-role="content"></section>',
            encoding="utf-8",
        )
        result = structural_check_deck(
            path,
            expected_units=["cover", "demand"],
            expected_page_counts={"cover": 1, "demand": 3},
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("demand" in error and "页数" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
