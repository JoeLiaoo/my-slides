"""Agent handoff, Design checks, and the review link for the slides stage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .design_deck import DECK_NAME, deck_dir, deck_fingerprint, disk_pages, page_unit, projects_root, unapproved_reports
from .design_engine import DEFAULT_BASE_URL, design_root, host_command, run_agent
from .project import now
from .units import Unit, load_units_manifest, unit_paths

CHECK_STATE = Path(".state") / "design-check.json"


def prepare_design_handoff(base: Path, root: Path, units: list[Unit]) -> list[Path]:
    """Write work/slides/<id>.md telling the agent to author Design pages from the approved report."""
    blocked = unapproved_reports(base, units)
    if blocked:
        raise ValueError("以下单元的报告尚未获得当前有效批准，不能准备写页：" + "、".join(blocked))
    engine = design_root()
    skill = f"{engine / 'skills' / 'slides' / 'SKILL.md'}" if engine else "<MY_SLIDES_DESIGN_ROOT>/skills/slides/SKILL.md"
    deck = deck_dir(base)
    outputs: list[Path] = []
    for unit in units:
        output = base / "work" / "slides" / f"{unit.id}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        report = unit_paths(base, unit.id).report.relative_to(base).as_posix()
        output.write_text("\n".join([
            f"# Design 写页交接：{unit.id}",
            "",
            f"项目目录：{root}",
            f"Deck 目录：{deck}",
            "",
            f"## {unit.title or unit.id}",
            f"- 大章节：{unit.chapter}",
            f"- 已批准报告：{report}（唯一内容来源）",
            f"- 页面文件：slides/{unit.id}.html；同单元的后续页命名为 slides/{unit.id}_2.html、slides/{unit.id}_3.html …",
            "",
            "## 规则",
            f"- 页面格式与版式按 Design+Slides 的 slides skill 写：{skill}（1920×1080，每页恰好一个 <section>，样式全部写在 style 属性）。",
            "- 只写报告里有出处的数字、引语和人名；缺的写成 `[待补：…]`，交付时列出。",
            "- 图表数字优先取自 research/numbers.md 已登记的条目，来源脚注沿用其中的“机构或作者《标题》（日期）”。",
            "- 动手前重新读目标页面：用户可能已在 127.0.0.1:5173 上手改过，在现有内容上改，不要整页重写。",
            "- 图片、图解用引擎根目录的 `npm run slides:import-asset -- <Deck 目录> <文件>` 导入，再把返回的 /_blob/<id> 写进页面。",
            "- 不要手改 deck.json 的 order/sections/cover：写完页面后由 `my-slides slides build` 按 units.json 同步。",
            "",
            "## 写完后",
            f"1. `my-slides slides build --unit {unit.id}`（同步页序与分节）",
            "2. `my-slides slides check --all`（Design 结构检查；加 --strict 时警告也算失败）",
            "3. `my-slides slides open`，请用户在 5173 上审阅；小改用户手调，大改按用户口述再改。",
            "",
        ]), encoding="utf-8")
        outputs.append(output)
    return outputs


def mapping_errors(base: Path, cfg: dict[str, Any]) -> tuple[list[Unit], list[str]]:
    units, errors = load_units_manifest(base, cfg.get("chapters"))
    if errors:
        raise ValueError("；".join(errors))
    unit_ids = {unit.id for unit in units}
    pages = disk_pages(deck_dir(base))
    missing = [unit.id for unit in units if not any(page_unit(page, unit_ids) == unit.id for page in pages)]
    return units, [f"单元 {unit_id} 还没有页面（slides/{unit_id}.html）" for unit_id in missing]


def check_deck(base: Path, cfg: dict[str, Any], *, strict: bool, render: bool) -> dict[str, Any]:
    """Design structure check (plus an optional light render pass) and unit coverage."""
    if not (deck_dir(base) / "deck.json").is_file():
        raise ValueError("Design deck 尚未创建：请先运行 my-slides slides build --all")
    _, errors = mapping_errors(base, cfg)
    flags = ["--strict"] if strict else []
    code, structure = run_agent(["check", DECK_NAME, *flags], projects_root(base))
    result: dict[str, Any] = {"structure": structure, "render": None}
    if code:
        errors.append(f"Design 检查未通过：{structure.get('code')}（{structure.get('errors', 0)} 个错误、"
                      f"{structure.get('warnings', 0)} 个警告）")
    if render:
        render_code, rendered = run_agent(["render-check", DECK_NAME, *flags], projects_root(base),
                                          base_url=DEFAULT_BASE_URL)
        result["render"] = rendered
        if render_code:
            errors.append(f"Design 渲染检查未通过：{rendered.get('code')} {rendered.get('message', '')}".strip())
    result["errors"] = errors
    result["valid"] = not errors
    _record_check(base, result, strict=strict, render=render)
    return result


def _record_check(base: Path, result: dict[str, Any], *, strict: bool, render: bool) -> None:
    path = base / CHECK_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fingerprint": deck_fingerprint(base), "valid": result["valid"], "errors": result["errors"],
               "strict": strict, "render": render, "checked_at": now()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_status(base: Path) -> dict[str, Any]:
    """Whether the last ``slides check`` passed for the deck exactly as it is now."""
    path = base / CHECK_STATE
    fingerprint = deck_fingerprint(base)
    try:
        record = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except json.JSONDecodeError:
        record = None
    if not isinstance(record, dict):
        return {"deck_exists": fingerprint is not None, "checked": False, "current": False, "last": None}
    return {
        "deck_exists": fingerprint is not None,
        "checked": True,
        "current": bool(record.get("valid") and fingerprint and record.get("fingerprint") == fingerprint),
        "last": record,
    }


def open_info(base: Path) -> dict[str, Any]:
    """Where the human reviews the deck, and the command that starts the host."""
    if not (deck_dir(base) / "deck.json").is_file():
        raise ValueError("Design deck 尚未创建：请先运行 my-slides slides build --all")
    _, doctor = run_agent(["doctor"], projects_root(base))
    _, opened = run_agent(["open", DECK_NAME], projects_root(base))
    return {
        "url": (opened.get("project") or {}).get("openUrl") or f"{DEFAULT_BASE_URL}/open/slides/{DECK_NAME}",
        "host_reachable": bool((doctor.get("host") or {}).get("reachable")),
        "engine_root": str(design_root()),
        "host_command": host_command(projects_root(base)),
        "deck_dir": str(deck_dir(base)),
    }
