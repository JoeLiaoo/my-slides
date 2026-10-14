"""Validation helpers for the project's reusable evidence number list."""

from __future__ import annotations

import re
from pathlib import Path


NUMBER_ROW_RE = re.compile(r"^\|\s*(N-\d{3,})\s*\|(.+?)\|\s*$")
SOURCE_RE = re.compile(r"^.+《[^《》]+》\（?\d{4}[^）]*\）$")
URL_RE = re.compile(r"https?://\S+")


def number_list_path(base: Path) -> Path:
    return base / "research" / "numbers.md"


def read_number_ids(base: Path) -> set[str]:
    path = number_list_path(base)
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = NUMBER_ROW_RE.match(line)
        if match:
            ids.add(match.group(1))
    return ids


def validate_number_list(base: Path) -> list[str]:
    path = number_list_path(base)
    if not path.is_file():
        return ["缺少数字证据清单：research/numbers.md；请先运行 my-slides prepare evidence-research"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    ids: set[str] = set()
    rows = [line for line in text.splitlines() if NUMBER_ROW_RE.match(line)]
    if not rows:
        errors.append("research/numbers.md：至少需要一条数字记录（表格行以 N-001 等编号开头）")
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = NUMBER_ROW_RE.match(line)
        if not match:
            continue
        number_id, body = match.groups()
        if number_id in ids:
            errors.append(f"research/numbers.md 第 {line_no} 行：编号重复 {number_id}")
        ids.add(number_id)
        cells = [cell.strip() for cell in body.split("|")]
        if len(cells) != 7:
            errors.append(f"research/numbers.md 第 {line_no} 行：每条记录须包含指标、数值、单位、期间、来源、URL、口径/估计七列")
            continue
        _, value, unit, period, source, url, scope = cells
        if not value or not unit or not period:
            errors.append(f"research/numbers.md 第 {line_no} 行：数值、单位和期间不能为空")
        if not SOURCE_RE.match(source):
            errors.append(f"research/numbers.md 第 {line_no} 行：来源须符合“机构或作者《标题》（日期）”格式")
        if not URL_RE.search(url):
            errors.append(f"research/numbers.md 第 {line_no} 行：请填写公开出处 URL")
        if not scope:
            errors.append(f"research/numbers.md 第 {line_no} 行：口径/估计请填写具体内容；无特殊限定时写“无”")
    return errors
