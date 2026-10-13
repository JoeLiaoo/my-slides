"""Tests for issue #38 PR 1 (02): Spec 布局意图 must be expanded into six sub-points."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from my_slides.commands.init import init_project
from my_slides.unit_workflow import validate_unit_spec
from my_slides.units import Unit, unit_paths, write_units_manifest


_COMPLETE_INTENT = """
### 布局意图
#### 读者问题
读者最关心什么
#### 唯一结论
带走一个判断
#### 关系类型
时间序列 + 结构构成
#### 主视觉
100% 堆叠条
#### 阅读顺序
标题 → 图 → 脚注
#### 选这个形式的原因
堆叠条看份额迁移
"""


def _spec_with_intent(unit_id: str, role: str, intent: str = _COMPLETE_INTENT) -> str:
    return (
        f"## Slide 1 — {unit_id}\n单元 ID：{unit_id}\n页面角色：{role}\n"
        "### 目的\nPurpose.\n### 核心结论\nConclusion.\n### 展示内容\nContent.\n"
        "### 证据与来源\nSource.\n### 限定条件\nLimits.\n### 报告段落映射\nMap.\n"
        f"{intent}"
        "### 图标需求\n无\n"
    )


class LayoutIntentValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        init_project(
            argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False)
        )

    def tearDown(self):
        self.temp.cleanup()

    def _seed(self, unit_id: str, role: str, spec_text: str) -> Unit:
        unit = Unit(id=unit_id, chapter="行业分析", role=role, title=unit_id)
        write_units_manifest(self.base, [unit])
        paths = unit_paths(self.base, unit_id)
        paths.report.parent.mkdir(parents=True, exist_ok=True)
        paths.spec.parent.mkdir(parents=True, exist_ok=True)
        paths.report.write_text(f"# {unit_id}\n\nLong enough. " * 6, encoding="utf-8")
        paths.spec.write_text(spec_text, encoding="utf-8")
        return unit

    def test_complete_intent_passes(self):
        unit = self._seed("complete", "content", _spec_with_intent("complete", "content"))
        self.assertEqual(validate_unit_spec(self.base, unit), [])

    def test_missing_subpoint_fails(self):
        intent = """
### 布局意图
#### 读者问题
Q
#### 唯一结论
A
#### 关系类型
时间序列
#### 主视觉
折线
#### 阅读顺序
标题 → 图
"""
        unit = self._seed("missing", "content", _spec_with_intent("missing", "content", intent=intent))
        errors = validate_unit_spec(self.base, unit)
        self.assertTrue(
            any("布局意图缺少 #### 选这个形式的原因" in err for err in errors),
            f"expected missing-subpoint error, got: {errors}",
        )

    def test_empty_subpoint_fails(self):
        intent = """
### 布局意图
#### 读者问题
Q
#### 唯一结论

#### 关系类型
时间序列
#### 主视觉
折线
#### 阅读顺序
标题 → 图
#### 选这个形式的原因
折线表达趋势
"""
        unit = self._seed("empty", "content", _spec_with_intent("empty", "content", intent=intent))
        errors = validate_unit_spec(self.base, unit)
        self.assertTrue(
            any("布局意图 → 唯一结论 不能为空" in err for err in errors),
            f"expected empty-subpoint error, got: {errors}",
        )

    def test_extra_subpoint_fails(self):
        intent = """
### 布局意图
#### 读者问题
Q
#### 唯一结论
A
#### 关系类型
时间序列
#### 主视觉
折线
#### 阅读顺序
标题 → 图
#### 选这个形式的原因
折线
#### 备注
extra
"""
        unit = self._seed("extra", "content", _spec_with_intent("extra", "content", intent=intent))
        errors = validate_unit_spec(self.base, unit)
        self.assertTrue(
            any("未识别的 #### 子标题" in err for err in errors),
            f"expected extra-subpoint error, got: {errors}",
        )

    def test_no_intent_fails(self):
        intent = """
### 布局意图
"""
        unit = self._seed("blank", "content", _spec_with_intent("blank", "content", intent=intent))
        errors = validate_unit_spec(self.base, unit)
        self.assertTrue(
            any("布局意图不能为空" in err for err in errors),
            f"expected empty-intent error, got: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
