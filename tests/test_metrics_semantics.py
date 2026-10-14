import unittest

from my_slides.metrics import bind_text, parse_page_metrics, validate_chart_metric_refs
from my_slides.rendering import validate_chart_spec


class MetricAndChartTests(unittest.TestCase):
    def test_page_local_metric_binding_and_chart_match(self):
        body = '```metric-spec\n{"version":1,"metrics":[{"id":"revenue","value":12.5,"unit":"亿元","period":"2025","source":"wiki/financials.md"}]}\n```'
        metrics = parse_page_metrics(body)
        self.assertEqual(bind_text('{{metric:revenue.value}} {{metric:revenue.unit}}', metrics, escape=True), '12.5 亿元')
        chart = {"type": "bar", "categories": ["2025"], "values": [12.5], "unit": "亿元", "metricRefs": ["revenue"]}
        validate_chart_metric_refs(chart, metrics)
        chart["values"] = [13]
        with self.assertRaisesRegex(ValueError, "不一致"):
            validate_chart_metric_refs(chart, metrics)
        with self.assertRaisesRegex(ValueError, "未批准"):
            bind_text('{{metric:other.value}}', metrics, escape=True)

    def test_semantic_failures_keep_negative_values_permitted(self):
        cases = [
            ({"type": "bar", "categories": ["A", "A"], "values": [1, 2]}, "重复"),
            ({"type": "line", "categories": ["2025-02-01", "2025-01-01"], "values": [1, 2], "categoryKind": "time"}, "时间"),
            ({"type": "stacked-bar", "categories": ["A"], "series": [{"name": "x", "values": [40]}, {"name": "y", "values": [30]}], "unit": "%", "compositionPercent": True}, "100%"),
            ({"type": "waterfall", "categories": ["A", "B", "C"], "values": [10, -3, 9], "totals": [2]}, "总计"),
            ({"type": "bar", "categories": ["A"], "values": [1], "axisMin": 1}, "零基线"),
        ]
        for chart, message in cases:
            with self.subTest(chart=chart), self.assertRaisesRegex(ValueError, message):
                validate_chart_spec(chart)
        validate_chart_spec({"type": "waterfall", "categories": ["A", "B", "C"], "values": [10, -3, 7], "totals": [2]})


if __name__ == "__main__":
    unittest.main()
