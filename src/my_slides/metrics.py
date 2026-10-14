"""Optional, page-local metric records from approved Spec pages."""

from __future__ import annotations

import html
import json
import math
import re
from typing import Any

METRIC_RE = re.compile(r"```metric-spec\s*\n(.*?)\n```", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\{\{metric:([a-z][a-z0-9_-]*)\.(value|unit|period|source|scope)\}\}")


def parse_page_metrics(body: str) -> dict[str, dict[str, Any]]:
    blocks = METRIC_RE.findall(body)
    if len(blocks) > 1:
        raise ValueError("每页最多一个 metric-spec 数据块")
    if not blocks:
        return {}
    try:
        payload = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise ValueError("metric-spec 必须是有效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("metrics"), list):
        raise ValueError("metric-spec 必须包含 version: 1 和 metrics 数组")
    result: dict[str, dict[str, Any]] = {}
    for item in payload["metrics"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", item["id"]):
            raise ValueError("metric id 必须是小写字母开头的安全标识")
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"metric {item['id']} 的 value 必须为有限数值")
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in ("unit", "period", "source")):
            raise ValueError(f"metric {item['id']} 必须填写 unit、period、source")
        if item["id"] in result:
            raise ValueError(f"重复 metric id：{item['id']}")
        result[item["id"]] = item
    return result


def bind_text(text: str, metrics: dict[str, dict[str, Any]], *, escape: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        ident, field = match.groups()
        if ident not in metrics:
            raise ValueError(f"未批准的 metric：{ident}")
        value = str(metrics[ident].get(field, ""))
        return html.escape(value) if escape else value

    bound = PLACEHOLDER_RE.sub(replace, text)
    if "{{metric:" in bound:
        raise ValueError("metric 占位符格式无效")
    return bound


def validate_chart_metric_refs(chart: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> None:
    refs = chart.get("metricRefs")
    if refs is None:
        return
    values = chart.get("values")
    if not isinstance(values, list) or not isinstance(refs, list) or len(refs) != len(values):
        raise ValueError("metricRefs 目前仅支持单系列 values，且需逐项对应")
    for index, ident in enumerate(refs):
        if not isinstance(ident, str) or ident not in metrics:
            raise ValueError(f"第 {index + 1} 项引用了未批准的 metric：{ident}")
        metric = metrics[ident]
        if values[index] != metric["value"] or chart.get("unit", "") != metric["unit"]:
            raise ValueError(f"第 {index + 1} 项与 metric {ident} 的数值或单位不一致")
