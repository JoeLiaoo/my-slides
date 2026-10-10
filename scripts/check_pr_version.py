#!/usr/bin/env python3
"""Validate a PR's version step and matching CHANGELOG entry."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_one_step_bump(base: str, proposed: str, *, allow_major: bool = False) -> bool:
    old = parse_version(base)
    new = parse_version(proposed)
    if old is None or new is None:
        return False
    major, minor, patch = old
    allowed = {
        (major, minor, patch + 1),
        (major, minor + 1, 0),
    }
    if allow_major:
        allowed.add((major + 1, 0, 0))
    return new in allowed


def changelog_version_section(changelog: str, version: str) -> str | None:
    section = re.compile(
        r"^##\s+\[" + re.escape(version) + r"\][^\n]*\n(?P<body>.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    ).search(changelog)
    if section is None:
        return None
    body = re.sub(r"<!--[\s\S]*?-->", "", section.group("body")).strip()
    return body or None


def changelog_has_version(changelog: str, version: str) -> bool:
    return changelog_version_section(changelog, version) is not None


def validate_version_change(
    base: str,
    proposed: str,
    changelog: str,
    *,
    allow_major: bool = False,
) -> list[str]:
    errors: list[str] = []
    if parse_version(base) is None:
        errors.append(f"base 版本 {base!r} 不是 X.Y.Z 格式")
    if parse_version(proposed) is None:
        errors.append(f"PR 版本 {proposed!r} 不是 X.Y.Z 格式")
    old = parse_version(base)
    new = parse_version(proposed)
    if not errors and not is_one_step_bump(base, proposed, allow_major=allow_major):
        allowed = "patch +1、minor +1 且 patch 归零"
        if allow_major:
            allowed += "，或 major +1 且 minor/patch 归零"
        errors.append(f"版本必须相对目标分支 {base} 前进一级（{allowed}）；当前 PR 为 {proposed}")
    section = changelog_version_section(changelog, proposed) if new is not None else None
    if new is not None and section is None:
        errors.append(f"CHANGELOG.md 缺少非空版本条目：## [{proposed}]")
    elif old is not None and new is not None and section is not None:
        breaking = re.search(r"^###\s+(?:Breaking Changes|不兼容变更)\s*$", section, re.MULTILINE) is not None
        if old[:2] != new[:2] and not breaking:
            errors.append("minor/major 升版必须在 CHANGELOG 条目中包含 `### Breaking Changes`（或 `### 不兼容变更`）")
        if old[:2] == new[:2] and breaking:
            errors.append("CHANGELOG 标记了不兼容变更；请升 minor 并将 patch 归零")
    return errors


def _version_from_pyproject(text: str) -> str:
    data = tomllib.loads(text)
    project = data.get("project")
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str):
        raise ValueError("pyproject.toml 缺少 [project].version")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True, help="PR 目标分支的本地 ref，例如 origin/main")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        base_toml = subprocess.run(
            ["git", "show", f"{args.base_ref}:pyproject.toml"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        current_toml = (root / "pyproject.toml").read_text(encoding="utf-8")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        base_version = _version_from_pyproject(base_toml)
        current_version = _version_from_pyproject(current_toml)
    except (OSError, subprocess.SubprocessError, tomllib.TOMLDecodeError, ValueError) as exc:
        print(f"版本检查无法运行：{exc}", file=sys.stderr)
        return 2

    allow_major = os.environ.get("MY_SLIDES_ALLOW_MAJOR_VERSION", "").lower() == "true"
    errors = validate_version_change(
        base_version,
        current_version,
        changelog,
        allow_major=allow_major,
    )
    if errors:
        print("PR 版本检查失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print(
            "请按 AGENTS.md 选择一个版本级别，并在 CHANGELOG.md 添加对应版本条目。"
            "major 版本需维护者给 PR 添加 version:major 标签。",
            file=sys.stderr,
        )
        return 1
    print(f"PR 版本检查通过：{base_version} → {current_version}；CHANGELOG 条目存在。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
