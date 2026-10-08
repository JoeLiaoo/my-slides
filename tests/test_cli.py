import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from my_slides.browser import check_deck
from my_slides.cli import (
    SlideFragmentParser,
    approval_is_current,
    approval_digest,
    approve_revision,
    browser_status,
    build_slides,
    install_agent_workflow,
    init_project,
    mark_ingested,
    prepare,
    project_root,
    render_assets,
    renderer_status,
    scan_sources,
    slug,
    slides_is_current,
    sync_wiki_index,
    template_chapters,
    validate_report,
    validate_chart_spec,
    validate_spec,
    validate_wiki,
)
from my_slides.units import resolve_local_markdown_path


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "my-slides"
        self.cfg = {"project": "Demo", "chapters": template_chapters()}

    def tearDown(self):
        self.temp.cleanup()

    def init(self):
        init_project(argparse.Namespace(project=str(self.root), source_dir=None, force=False, json=False))

    @staticmethod
    def spec_page(chapter, role="content", number=1):
        return (
            f"## Slide {number} — {chapter}\n页面 ID：{slug(chapter)}-{number:02d}\n页面角色：{role}\n"
            "### 目的\nExplain the decision.\n### 核心结论\nEvidence supports the conclusion.\n"
            "### 展示内容\nSummary of approved report content.\n### 证据与来源\nSource link.\n"
            "### 限定条件\nState limits.\n### 报告段落映射\nMap to the report section.\n"
            "### 布局意图\nClear headline and supporting evidence.\n### 图标需求\n无\n"
        )

    def test_default_wiki_index_matches_report_chapters(self):
        self.init()
        self.assertEqual(validate_wiki(self.base, self.cfg), [])
        index = self.base / "wiki" / "index.md"
        index.write_text("# Wiki Index\n\n## 其他\n", encoding="utf-8")
        self.assertTrue(any("缺少报告章节分组" in error for error in validate_wiki(self.base, self.cfg)))

    def test_agent_skill_install_preserves_existing_instructions(self):
        existing = self.root / ".agents" / "skills" / "my-slides-workflow" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("user edit", encoding="utf-8")
        result = install_agent_workflow(self.root)
        self.assertEqual(existing.read_text(encoding="utf-8"), "user edit")
        self.assertIn(".agents/skills/my-slides-workflow/SKILL.md", result["preserved"])
        claude_skill = self.root / ".claude" / "skills" / "my-slides-workflow" / "SKILL.md"
        self.assertTrue(claude_skill.is_file())

    def test_project_commands_can_resolve_from_nested_directory(self):
        self.init()
        nested = self.root / "nested" / "work"
        nested.mkdir(parents=True)
        original = Path.cwd()
        try:
            import os
            os.chdir(nested)
            self.assertEqual(project_root(None), self.root.resolve())
        finally:
            os.chdir(original)

    def test_wiki_lint_reports_unindexed_topic_page(self):
        self.init()
        (self.base / "wiki" / "company.md").write_text("# Company\n\nA topic page.\n", encoding="utf-8")
        self.assertTrue(any("尚未加入索引" in error for error in validate_wiki(self.base, self.cfg)))
        index = self.base / "wiki" / "index.md"
        index.write_text(index.read_text(encoding="utf-8").replace("## 补充研究", "## 投资概要\n\n- [Company](company.md)\n\n## 补充研究"), encoding="utf-8")
        self.assertEqual(validate_wiki(self.base, self.cfg), [])

    def test_index_sync_adds_configured_chapters_without_overwriting_pages(self):
        self.init()
        index = self.base / "wiki" / "index.md"
        original = index.read_text(encoding="utf-8")
        index.write_text(original + "\nManual note preserved.\n", encoding="utf-8")
        chapters = self.cfg["chapters"] + ["新增章节"]
        sync_wiki_index(index, chapters)
        updated = index.read_text(encoding="utf-8")
        self.assertIn("Manual note preserved.", updated)
        self.assertIn("## 新增章节", updated)
        self.assertIn("## 补充研究", updated)

    def test_source_changes_and_removals_require_acknowledgement(self):
        self.init()
        source = self.root / "memo.md"
        source.write_text("initial", encoding="utf-8")
        _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
        self.assertEqual(pending, ["memo.md"])
        self.assertEqual(removed, [])
        self.assertEqual(mark_ingested(self.base, pending), 1)
        source.unlink()
        for _ in range(2):
            _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
            self.assertEqual(pending, [])
            self.assertEqual(removed, ["memo.md"])
        self.assertEqual(mark_ingested(self.base, removed), 1)
        _, _, removed = scan_sources(self.root, self.base, {"source_dirs": ["."]})
        self.assertEqual(removed, [])

    def test_report_prepare_captures_a_wiki_content_snapshot(self):
        self.init()
        args = argparse.Namespace(project=str(self.root), kind="report", question=None, json=False)
        self.assertEqual(prepare(args), 0)
        snapshots = list((self.base / ".state" / "snapshots" / "wiki").glob("*/manifest.json"))
        self.assertEqual(len(snapshots), 1)
        manifest = json.loads(snapshots[0].read_text(encoding="utf-8"))
        self.assertIn("index.md", {item["path"] for item in manifest["files"]})
        task = next((self.base / "work").glob("*-report.md")).read_text(encoding="utf-8")
        self.assertIn(".state/snapshots/wiki/", task)

    def test_source_change_invalidates_approved_report(self):
        source = self.root / "source.md"
        source.write_text("Initial facts.", encoding="utf-8")
        self.init()
        _, pending, _ = scan_sources(self.root, self.base, {"source_dirs": ["."]})
        self.assertEqual(mark_ingested(self.base, pending), 1)
        for chapter in self.cfg["chapters"]:
            (self.base / "reports" / f"{slug(chapter)}.md").write_text(
                f"# {chapter}\n\n" + "Evidence-backed report text. " * 4, encoding="utf-8"
            )
        _, errors = approve_revision(self.base, self.cfg, "report")
        self.assertEqual(errors, [])
        self.assertTrue(approval_is_current(self.base, "report", self.cfg))
        source.write_text("Changed facts.", encoding="utf-8")
        self.assertFalse(approval_is_current(self.base, "report", self.cfg))

    def test_report_revision_invalidates_spec_approval(self):
        self.init()
        for chapter in self.cfg["chapters"]:
            (self.base / "reports" / f"{slug(chapter)}.md").write_text(
                f"# {chapter}\n\n" + "Evidence-backed report text. " * 4, encoding="utf-8"
            )
        self.assertEqual(validate_report(self.base, self.cfg), [])
        report_digest, errors = approve_revision(self.base, self.cfg, "report")
        self.assertTrue(report_digest)
        self.assertEqual(errors, [])
        self.assertTrue((self.base / ".state" / "revisions" / "report" / report_digest / "manifest.json").exists())
        for chapter in self.cfg["chapters"]:
            (self.base / "specs" / f"{slug(chapter)}.md").write_text(
                self.spec_page(chapter, "cover" if chapter == self.cfg["chapters"][0] else "content"), encoding="utf-8"
            )
        self.assertEqual(validate_spec(self.base, self.cfg), [])
        _, errors = approve_revision(self.base, self.cfg, "spec")
        self.assertEqual(errors, [])
        self.assertTrue(approval_is_current(self.base, "spec", self.cfg))
        report = self.base / "reports" / f"{slug(self.cfg['chapters'][0])}.md"
        report.write_text(report.read_text(encoding="utf-8") + "\nUpdated.", encoding="utf-8")
        self.assertFalse(approval_is_current(self.base, "report", self.cfg))
        self.assertFalse(approval_is_current(self.base, "spec", self.cfg))

    def test_spec_requires_one_opening_cover_and_project_unique_page_ids(self):
        self.init()
        for chapter in self.cfg["chapters"]:
            role = "cover" if chapter == self.cfg["chapters"][0] else "content"
            (self.base / "specs" / f"{slug(chapter)}.md").write_text(self.spec_page(chapter, role), encoding="utf-8")
        second = self.base / "specs" / f"{slug(self.cfg['chapters'][1])}.md"
        second.write_text(self.spec_page(self.cfg["chapters"][1], "content").replace(
            f"{slug(self.cfg['chapters'][1])}-01", f"{slug(self.cfg['chapters'][0])}-01"
        ), encoding="utf-8")
        errors = validate_spec(self.base, self.cfg)
        self.assertTrue(any("页面 ID 重复" in error for error in errors), errors)
        second.write_text(self.spec_page(self.cfg["chapters"][1], "cover"), encoding="utf-8")
        errors = validate_spec(self.base, self.cfg)
        self.assertTrue(any("只能包含一个 cover" in error for error in errors), errors)

    def test_slide_build_requires_valid_notes(self):
        self.init()
        # A one-chapter configuration keeps this test focused on the HTML contract.
        cfg = {"project": "Demo", "chapters": [self.cfg["chapters"][0]]}
        fragment = self.base / "slides" / "chapters" / f"{slug(cfg['chapters'][0])}.html"
        fragment.write_text('<section class="slide"><h1>Demo</h1></section>', encoding="utf-8")
        output, errors = build_slides(self.base, cfg)
        self.assertIsNone(output)
        self.assertTrue(any("slide-notes" in error for error in errors))
        fragment.write_text(
            '<section class="slide"><h1>Demo</h1>'
            '<script type="application/json" class="slide-notes">{"title":"Demo","script":"Present the demo.","notes":[]}</script>'
            "</section>",
            encoding="utf-8",
        )
        output, errors = build_slides(self.base, cfg)
        self.assertEqual(errors, [])
        self.assertTrue(output.exists())

    def test_chart_specs_reject_missing_values_and_incompatible_units(self):
        with self.assertRaisesRegex(ValueError, "缺失值"):
            validate_chart_spec({"type": "bar", "categories": ["A", "B"], "values": [1, None]})
        with self.assertRaisesRegex(ValueError, "单位"):
            validate_chart_spec({"type": "multi-line", "categories": ["A"], "unit": "元", "series": [
                {"name": "收入", "unit": "万元", "values": [1]}
            ]})

    def test_slides_chart_data_must_match_spec_exactly(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        spec = {"type": "bar", "categories": ["2024", "2025"], "values": [10, 14], "unit": "亿元"}
        (self.base / "specs" / f"{slug(chapter)}.md").write_text(
            self.spec_page(chapter).replace("### 布局意图", "```echarts-spec\n" + json.dumps(spec, ensure_ascii=False) + "\n```\n### 布局意图"),
            encoding="utf-8",
        )
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            '<section class="slide" data-page-role="content"><h1>Approved data</h1>'
            '<script type="application/json" class="mls-echarts-spec">'
            '{"type":"bar","categories":["2024","2025"],"values":[10,15],"unit":"亿元"}'
            '</script><script type="application/json" class="slide-notes">{"title":"Chart","script":"Explain the chart","notes":[]}</script></section>',
            encoding="utf-8",
        )
        output, errors = build_slides(self.base, cfg)
        self.assertIsNone(output)
        self.assertTrue(any("完全一致" in error for error in errors), errors)

    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    def test_pinned_renderers_emit_local_chart_and_icon_svg(self):
        output = render_assets([
            {"id": "chart", "kind": "chart", "spec": {"type": "bar", "title": "Revenue", "categories": ["2024", "2025"], "values": [10, 14], "unit": "亿元"}},
            {"id": "icon", "kind": "icon", "spec": {"name": "arrow-right", "color": "#A6192E", "size": 24}},
        ])
        self.assertIn("<svg", output["chart"])
        self.assertIn("Revenue", output["chart"])
        self.assertIn("<svg", output["icon"])
        self.assertIn("arrow-right", output["icon"])

    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    def test_all_supported_chart_types_render_to_svg(self):
        shared = {"categories": ["A", "B"], "unit": "亿元", "source": "synthetic-source.md"}
        specs = [
            {**shared, "type": "bar", "values": [1, 2]},
            {**shared, "type": "dot", "values": [1, 2]},
            {**shared, "type": "line", "values": [1, 2]},
            {**shared, "type": "multi-line", "series": [{"name": "Actual", "values": [1, 2]}, {"name": "Plan", "values": [2, 3]}]},
            {"type": "scatter", "xUnit": "亿元", "yUnit": "%", "points": [{"x": 1, "y": 20}, {"x": 2, "y": 25}], "source": "synthetic-source.md"},
            {"type": "time-scatter", "xUnit": "date", "yUnit": "亿元", "points": [{"date": "2025-01-01", "y": 1}, {"date": "2025-06-01", "y": 2}], "source": "synthetic-source.md"},
            {**shared, "type": "stacked-bar", "series": [{"name": "A", "values": [1, 2]}, {"name": "B", "values": [2, 3]}]},
            {**shared, "type": "waterfall", "categories": ["Start", "Change", "End"], "values": [10, -2, 8], "totals": [0, 2]},
        ]
        rendered = render_assets([{"id": f"chart-{i}", "kind": "chart", "spec": spec} for i, spec in enumerate(specs)])
        self.assertEqual(len(rendered), 8)
        self.assertTrue(all(value.startswith("<svg") for value in rendered.values()))

    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    @unittest.skipUnless(browser_status()["chromium_installed"], "optional Playwright Chromium browser is not installed")
    def test_full_chart_icon_slide_build_is_offline_and_archives_rebuilds(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        report = self.base / "reports" / f"{slug(chapter)}.md"
        report.write_text("# Approved report\n\nRevenue increased from 10 to 14 billion yuan. Source: public filing.\n", encoding="utf-8")
        _, errors = approve_revision(self.base, cfg, "report")
        self.assertEqual(errors, [])
        chart = {"type": "bar", "title": "Revenue", "categories": ["2024", "2025"], "values": [10, 14], "unit": "亿元", "source": f"../reports/{slug(chapter)}.md"}
        spec = self.spec_page(chapter, "cover") + self.spec_page(chapter, "content", 2).replace(
            "### 布局意图", "```echarts-spec\n" + json.dumps(chart, ensure_ascii=False) + "\n```\n### 布局意图"
        ).replace("### 图标需求\n无", "### 图标需求\narrow-right")
        (self.base / "specs" / f"{slug(chapter)}.md").write_text(spec, encoding="utf-8")
        _, errors = approve_revision(self.base, cfg, "spec")
        self.assertEqual(errors, [])
        fragment = self.base / "slides" / "chapters" / f"{slug(chapter)}.html"
        fragment.write_text(
            '<section class="slide active" data-page-role="cover"><h1>Demo investment report</h1>'
            '<script type="application/json" class="slide-notes">{"title":"Cover","script":"Introduce the project.","notes":[]}</script></section>'
            '<section class="slide" data-page-role="content"><h1>Revenue</h1>'
            '<script type="application/json" class="mls-echarts-spec">' + json.dumps(chart, ensure_ascii=False) + '</script>'
            '<script type="application/json" class="mls-lucide-spec">{"name":"arrow-right"}</script>'
            '<script type="application/json" class="slide-notes">{"title":"Revenue","script":"Revenue grew.","notes":["10 to 14"]}</script>'
            '</section>', encoding="utf-8"
        )
        output, errors = build_slides(self.base, cfg)
        self.assertEqual(errors, [])
        generated = output.read_text(encoding="utf-8")
        self.assertIn("<svg", generated)
        self.assertIn("third-party-notices", generated)
        self.assertNotIn("mls-echarts-spec", generated)
        browser_result = check_deck(output)
        self.assertTrue(browser_result["valid"], browser_result)
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            fragment.read_text(encoding="utf-8").replace("<h1>Revenue</h1>", "<h1>Revenue revised</h1>"), encoding="utf-8"
        )
        _, errors = build_slides(self.base, cfg)
        self.assertEqual(errors, [])
        archive = self.base / ".state" / "deliveries"
        self.assertTrue(any(archive.glob("*.html")))

    @unittest.skipUnless(renderer_status()["ready"], "optional local Node render dependencies are not installed")
    @unittest.skipUnless(browser_status()["chromium_installed"], "optional Playwright Chromium browser is not installed")
    def test_synthetic_six_chapter_project_end_to_end(self):
        sources = self.root / "sources"
        sources.mkdir()
        (sources / "metrics.md").write_text("# Synthetic metrics\nRevenue: 10, 14, 19. Margin: 20%, 22%, 24%.\n", encoding="utf-8")
        init_project(argparse.Namespace(project=str(self.root), source_dir=["sources"], force=False, json=False))
        wiki_page = self.base / "wiki" / "company.md"
        wiki_page.write_text("# Synthetic company\n\nRevenue and margin trend [from the synthetic source](../../sources/metrics.md).\n", encoding="utf-8")
        index = self.base / "wiki" / "index.md"
        index.write_text(index.read_text(encoding="utf-8").replace("## 投资概要", "## 投资概要\n\n- [Synthetic company](company.md) — business and financial summary"), encoding="utf-8")
        self.assertEqual(validate_wiki(self.base, self.cfg), [])
        _, pending, removed = scan_sources(self.root, self.base, {"source_dirs": ["sources"]})
        self.assertEqual(pending, ["sources/metrics.md"])
        self.assertEqual(mark_ingested(self.base, pending), 1)
        self.assertEqual(prepare(argparse.Namespace(project=str(self.root), kind="report", question=None, json=False)), 0)

        finance_chapter = "财务分析与回报分析"
        chart = {"type": "line", "title": "Revenue trend", "categories": ["2024", "2025", "2026"], "values": [10, 14, 19], "unit": "亿元", "source": "../../sources/metrics.md"}
        for chapter in self.cfg["chapters"]:
            report_path = self.base / "reports" / f"{slug(chapter)}.md"
            report_path.write_text(
                f"# {chapter}\n\nSynthetic example: supported analysis with explicit assumptions. [Source](../../sources/metrics.md).\n",
                encoding="utf-8",
            )
            role = "cover" if chapter == self.cfg["chapters"][0] else "content"
            spec_text = self.spec_page(chapter, role).replace("Source link.", f"[Approved report](../reports/{report_path.name})")
            if chapter == finance_chapter:
                spec_text = spec_text.replace("### 布局意图", "```echarts-spec\n" + json.dumps(chart, ensure_ascii=False) + "\n```\n### 布局意图")
            if chapter == "投资概要":
                spec_text = spec_text.replace("### 图标需求\n无", "### 图标需求\narrow-right")
            (self.base / "specs" / f"{slug(chapter)}.md").write_text(spec_text, encoding="utf-8")
        self.assertEqual(validate_report(self.base, self.cfg), [])
        _, errors = approve_revision(self.base, self.cfg, "report")
        self.assertEqual(errors, [])
        self.assertEqual(prepare(argparse.Namespace(project=str(self.root), kind="spec", question=None, json=False)), 0)
        self.assertEqual(validate_spec(self.base, self.cfg), [])
        _, errors = approve_revision(self.base, self.cfg, "spec")
        self.assertEqual(errors, [])
        self.assertEqual(prepare(argparse.Namespace(project=str(self.root), kind="slides", question=None, json=False)), 0)

        for chapter in self.cfg["chapters"]:
            fragment = self.base / "slides" / "chapters" / f"{slug(chapter)}.html"
            role = "cover" if chapter == self.cfg["chapters"][0] else "content"
            body = '<section class="slide active" data-page-role="' + role + '"><h1>' + chapter + '</h1><p>Synthetic investment committee summary.</p>'
            if chapter == finance_chapter:
                body += '<script type="application/json" class="mls-echarts-spec">' + json.dumps(chart, ensure_ascii=False) + '</script>'
            if chapter == "投资概要":
                body += '<script type="application/json" class="mls-lucide-spec">{"name":"arrow-right"}</script>'
            body += '<script type="application/json" class="slide-notes">' + json.dumps({"title": chapter, "script": "Synthetic example for workflow validation.", "notes": ["All values are fictional."]}, ensure_ascii=False) + '</script></section>'
            fragment.write_text(body, encoding="utf-8")
        output, errors = build_slides(self.base, self.cfg)
        self.assertEqual(errors, [])
        self.assertEqual(output.read_text(encoding="utf-8").count('class="slide '), 6)
        state = json.loads((self.base / ".state" / "slides.json").read_text(encoding="utf-8"))
        diagnostics = {"state": state, "report_current": approval_is_current(self.base, "report", self.cfg),
                       "spec_current": approval_is_current(self.base, "spec", self.cfg),
                       "report_digest": approval_digest(self.base, "report", self.cfg),
                       "spec_digest": approval_digest(self.base, "spec", self.cfg)}
        self.assertTrue(slides_is_current(self.base, self.cfg), diagnostics)
        browser_result = check_deck(output)
        self.assertTrue(browser_result["valid"], browser_result)
        command = subprocess.run(
            [sys.executable, "-m", "my_slides.cli", "slides", "check", "--browser", "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", env=os.environ.copy(),
        )
        self.assertEqual(command.returncode, 0, command.stderr + command.stdout)
        self.assertTrue(json.loads(command.stdout)["valid"])

    def _notes(self, title="Demo"):
        return (
            f'<script type="application/json" class="slide-notes">'
            f'{{"title":"{title}","script":"Present.","notes":[]}}</script>'
        )

    def test_slide_security_rejects_javascript_entity_bypass(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            f'<section class="slide"><a href="java&#9;script:void(window.PWN=1)">x</a>{self._notes()}</section>',
            encoding="utf-8",
        )
        output, errors = build_slides(self.base, cfg)
        self.assertIsNone(output)
        self.assertTrue(any("不安全链接" in error or "javascript" in error.lower() for error in errors), errors)

    def test_slide_security_rejects_form_action_javascript(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            f'<section class="slide"><form action="javascript:void(window.PWN=1)"><button>go</button></form>{self._notes()}</section>',
            encoding="utf-8",
        )
        output, errors = build_slides(self.base, cfg)
        self.assertIsNone(output)
        self.assertTrue(any("form" in error.lower() for error in errors), errors)

    def test_slide_security_rejects_meta_refresh_and_external_media(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        fragment = self.base / "slides" / "chapters" / f"{slug(chapter)}.html"
        fragment.write_text(
            f'<section class="slide"><meta http-equiv="refresh" content="0;url=https://evil.example">{self._notes()}</section>',
            encoding="utf-8",
        )
        _, errors = build_slides(self.base, cfg)
        self.assertTrue(any("meta" in error.lower() for error in errors), errors)
        fragment.write_text(
            f'<section class="slide"><video poster="https://evil.example/p.png"></video>{self._notes()}</section>',
            encoding="utf-8",
        )
        _, errors = build_slides(self.base, cfg)
        self.assertTrue(any("video" in error.lower() or "不安全" in error for error in errors), errors)
        fragment.write_text(
            f'<section class="slide"><svg><image href="https://evil.example/i.png"></image></svg>{self._notes()}</section>',
            encoding="utf-8",
        )
        _, errors = build_slides(self.base, cfg)
        self.assertTrue(any("不安全链接" in error or "image" in error.lower() for error in errors), errors)

    def test_slide_merge_preserves_active_in_body_text(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        cfg = {"project": "Demo", "chapters": [chapter]}
        (self.base / "slides" / "chapters" / f"{slug(chapter)}.html").write_text(
            f'<section class="slide active" data-page-role="cover"><h1>Cover</h1>{self._notes("Cover")}</section>'
            f'<section class="slide active" data-page-role="content">'
            f"<p>The market is active today</p>{self._notes('Body')}</section>",
            encoding="utf-8",
        )
        output, errors = build_slides(self.base, cfg)
        self.assertEqual(errors, [])
        html_text = output.read_text(encoding="utf-8")
        self.assertIn("The market is active today", html_text)
        # Second slide must not keep the root active class, but body text stays.
        second = html_text.split('data-slide="1"', 1)[1]
        self.assertNotRegex(second.split("</section>", 1)[0], r'class="[^"]*\bactive\b')

    def test_v1_report_accepts_percent_encoded_local_links(self):
        self.init()
        chapter = self.cfg["chapters"][0]
        report = self.base / "reports" / f"{slug(chapter)}.md"
        wiki_notes = self.base / "wiki" / "my notes.md"
        wiki_notes.write_text("# Notes\n", encoding="utf-8")
        report.write_text(
            f"# {chapter}\n\nEnough report text with a link to [notes](../wiki/my%20notes.md).\n",
            encoding="utf-8",
        )
        self.assertEqual(validate_report(self.base, {"chapters": [chapter]}), [])
        resolved = resolve_local_markdown_path("../wiki/my%20notes.md", report)
        self.assertEqual(resolved, wiki_notes.resolve())


if __name__ == "__main__":
    unittest.main()
