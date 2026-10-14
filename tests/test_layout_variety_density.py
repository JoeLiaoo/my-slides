"""Deck-wide layout rhythm and one-use evidence ID rules for issue #47."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.unit_workflow import validate_deck_spec, validate_unit_spec
from my_slides.units import Unit, unit_paths, write_units_manifest


def _page(unit_id: str, role: str, layout: str, *, number_id: str | None = None, key: bool = False) -> str:
    judgment = "### 我们的判断 / 对投资的含义\n作者判断。\n" if key else ""
    evidence = f"数据编号：{number_id}\n" if number_id else ""
    key_line = "关键页：是\n" if key else ""
    return (
        f"单元 ID：{unit_id}\n页面角色：{role}\n\n## Slide 1 — {unit_id}\n"
        f"内容类型：{'判断/收束' if key else '案例'}\n版式：{layout}\n"
        f"{key_line}"
        "### 目的\n说明。\n### 核心结论\n结论。\n"
        f"{judgment}### 展示内容\n表格或结构图。\n{evidence}"
        "### 证据与来源\n证据。\n### 限定条件\n无。\n### 报告段落映射\n报告。\n"
        "### 布局意图\n#### 读者问题\n问题\n#### 唯一结论\n结论\n#### 关系类型\n关系\n"
        "#### 主视觉\n结构图\n#### 阅读顺序\n标题到图\n#### 选这个形式的原因\n匹配关系\n"
        "### 图标需求\n无\n### 来源脚注\n作者《研究记录》（2026）。\n"
    )


class DeckLayoutRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))
        self.units = [
            Unit(id="cover", chapter="投资概要", role="cover"),
            Unit(id="trend", chapter="行业", role="content"),
            Unit(id="matrix", chapter="行业", role="content"),
            Unit(id="case", chapter="公司", role="content"),
        ]
        write_units_manifest(self.base, self.units)
        layouts = ["KPI卡片", "100%堆叠趋势", "敏感性热图", "静态机制图"]
        for unit, layout in zip(self.units, layouts, strict=True):
            unit_paths(self.base, unit.id).spec.write_text(_page(unit.id, unit.role, layout), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_layout_fields_and_optional_numbers_and_judgment(self):
        self.assertEqual(validate_unit_spec(self.base, self.units[1]), [])
        self.assertEqual(validate_deck_spec(self.base), [])

    def test_repeated_number_id_across_units_is_rejected(self):
        for unit in self.units[1:3]:
            unit_paths(self.base, unit.id).spec.write_text(
                _page(unit.id, unit.role, "哑铃对比", number_id="N-001"), encoding="utf-8"
            )
        errors = validate_deck_spec(self.base)
        self.assertTrue(any("N-001" in error and "重复引用" in error for error in errors), errors)

    def test_three_consecutive_layouts_are_rejected_and_variety_floor_is_enforced(self):
        for unit in self.units[1:]:
            unit_paths(self.base, unit.id).spec.write_text(
                _page(unit.id, unit.role, "哑铃对比"), encoding="utf-8"
            )
        errors = validate_deck_spec(self.base)
        self.assertTrue(any("连续超过 2 页" in error for error in errors), errors)
        self.assertTrue(any("至少需要" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
