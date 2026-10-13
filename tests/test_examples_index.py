"""Tests for the bundled example library index and the prepare-slides handoff."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.examples_index import (
    format_matches,
    load_examples_index,
    select_examples,
)
from my_slides.unit_workflow import prepare_unit_handoff
from my_slides.units import Unit, unit_paths, write_units_manifest


_LAYOUT_INTENT = """
### 布局意图
#### 读者问题
{question}
#### 唯一结论
{conclusion}
#### 关系类型
{relation}
#### 主视觉
{visual}
#### 阅读顺序
{order}
#### 选这个形式的原因
{reason}
"""


def _spec(unit_id: str, role: str, *, intent: str = "") -> str:
    return (
        f"## Slide 1 — {unit_id}\n单元 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nPurpose.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        f"{_LAYOUT_INTENT.format_map(intent) if intent else '### 布局意图\n无\n'}"
        "### 图标需求\n无\n"
    )


class ExamplesIndexTests(unittest.TestCase):
    def test_load_examples_index_has_six_categories(self):
        index = load_examples_index()
        self.assertGreaterEqual(len(index), 6)
        ids = {entry["id"] for entry in index}
        # One example per default category from issue #38 PR 1 (05).
        expected_categories = {
            "investment-summary-cover-kpis",
            "market-trend-pivot",
            "competition-dumbbell",
            "technology-funnel",
            "unit-economics-payback",
            "financial-scenario-sensitivity",
        }
        self.assertTrue(expected_categories.issubset(ids))

    def test_select_examples_matches_pivot_signals(self):
        spec = _spec(
            "market-trend",
            "content",
            intent={
                "question": "行业拐点是哪一年",
                "conclusion": "2022 年云端调度份额首次突破 30%",
                "relation": "时间序列 + 结构构成",
                "visual": "100% 堆叠条",
                "order": "标题 → 图",
                "reason": "堆叠条能跨年比较份额迁移",
            },
        )
        matches = select_examples(spec)
        self.assertTrue(matches)
        self.assertEqual(matches[0].id, "market-trend-pivot")
        # At least one signal matched.
        self.assertTrue(any(s in {"拐点", "占比", "份额", "迁移"} for s in matches[0].matched_signals))

    def test_select_examples_deduplicates(self):
        spec = _spec(
            "market-trend",
            "content",
            intent={
                "question": "行业拐点",
                "conclusion": "2022",
                "relation": "时间序列 + 结构构成",
                "visual": "100% 堆叠条",
                "order": "标题 → 图",
                "reason": "堆叠条",
            },
        )
        matches = select_examples(spec, limit=2)
        paths = [m.path for m in matches]
        self.assertEqual(len(paths), len(set(paths)))

    def test_select_examples_empty_spec_returns_default(self):
        matches = select_examples("", limit=2)
        self.assertTrue(matches)
        # Default fallback entry points to the market-trend pivot.
        self.assertEqual(matches[0].path, "examples/market-trend/01-pivot-share-shift")

    def test_format_matches_returns_markdown(self):
        matches = select_examples("")
        rendered = format_matches(matches)
        self.assertTrue(rendered.startswith("- `"))
        self.assertIn("examples/market-trend/01-pivot-share-shift", rendered)


class PrepareSlidesHandoffExamplesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(
            argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False)
        )

    def tearDown(self):
        self.temp.cleanup()

    def _seed_unit(self, unit_id: str, role: str, spec_text: str) -> Unit:
        unit = Unit(id=unit_id, chapter="行业分析", role=role, title=unit_id)
        write_units_manifest(self.base, [unit])
        paths = unit_paths(self.base, unit_id)
        paths.report.parent.mkdir(parents=True, exist_ok=True)
        paths.spec.parent.mkdir(parents=True, exist_ok=True)
        paths.page.parent.mkdir(parents=True, exist_ok=True)
        paths.report.write_text(
            f"# {unit_id}\n\n" + "Detailed text. " * 6 + "\n", encoding="utf-8"
        )
        paths.spec.write_text(spec_text, encoding="utf-8")
        paths.page.write_text(
            f'<section class="slide" data-unit-id="{unit_id}" data-page-role="{role}">'
            f'<h1>{unit_id}</h1>'
            f'<script type="application/json" class="slide-notes">'
            f'{{"title":"{unit_id}","notes":[]}}</script></section>',
            encoding="utf-8",
        )
        return unit

    def test_prepare_slides_includes_relevant_examples(self):
        unit = self._seed_unit(
            "market-trend",
            "content",
            _spec(
                "market-trend",
                "content",
                intent={
                    "question": "行业拐点是哪一年",
                    "conclusion": "2022 年云端调度份额首次突破 30%",
                    "relation": "时间序列 + 结构构成",
                    "visual": "100% 堆叠条",
                    "order": "标题 → 图",
                    "reason": "堆叠条能跨年比较份额迁移",
                },
            ),
        )
        outputs = prepare_unit_handoff(self.base, self.root, [unit], "slides")
        self.assertEqual(len(outputs), 1)
        text = outputs[0].read_text(encoding="utf-8")
        self.assertIn("相关参考案例", text)
        # The pivot example should be matched; the cover example should not.
        self.assertIn("examples/market-trend/01-pivot-share-shift", text)
        # The handoff must not include unrelated category paths.
        self.assertNotIn("examples/competition/01-dumbbell", text)

    def test_prepare_slides_falls_back_when_spec_missing(self):
        unit = Unit(id="cover", chapter="投资概要", role="cover", title="cover")
        write_units_manifest(self.base, [unit])
        paths = unit_paths(self.base, "cover")
        paths.report.parent.mkdir(parents=True, exist_ok=True)
        paths.spec.parent.mkdir(parents=True, exist_ok=True)
        paths.page.parent.mkdir(parents=True, exist_ok=True)
        paths.report.write_text("# cover\n\n" + "Body. " * 6, encoding="utf-8")
        paths.page.write_text(
            '<section class="slide" data-unit-id="cover" data-page-role="cover">'
            '<h1>cover</h1>'
            '<script type="application/json" class="slide-notes">'
            '{"title":"cover","notes":[]}</script></section>',
            encoding="utf-8",
        )
        outputs = prepare_unit_handoff(self.base, self.root, [unit], "slides")
        text = outputs[0].read_text(encoding="utf-8")
        # Without a spec on disk, the fallback must still surface an example.
        self.assertIn("相关参考案例", text)
        self.assertIn("examples/", text)


if __name__ == "__main__":
    unittest.main()
