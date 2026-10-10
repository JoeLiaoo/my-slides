#!/usr/bin/env python3
"""Validate version steps, changelog entries, and release tags."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SKIP_PREFIXES = (".github/", "tests/", "scripts/")
ZERO_SHA = "0" * 40


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


def is_skippable_change(paths: list[str]) -> bool:
    """True when every changed path is CI, tests, or version-tooling only."""
    if not paths:
        return False
    return all(path.replace("\\", "/").startswith(SKIP_PREFIXES) for path in paths)


def validate_main_advance(
    parent: str,
    head: str,
    paths: list[str],
    changelog: str,
    *,
    allow_major: bool = True,
) -> list[str]:
    """Catch a merge that landed without advancing the version.

    Two PRs can both pass the PR check against the same base version. Git then
    treats identical version-line edits as conflict-free, so the second merge
    can arrive with the version unchanged.
    """
    if parent == head and is_skippable_change(paths):
        return []
    if parent == head:
        shown = "、".join(paths[:8]) or "（没有文件差异）"
        return [
            f"合并后版本号仍是 {head}，但改动不在可跳过范围（.github/、tests/、scripts/）：{shown}。"
            "请补一个只升版本并写更新日志的 PR。"
        ]
    return validate_version_change(parent, head, changelog, allow_major=allow_major)


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


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def changed_paths(repo: Path, base_ref: str, head: str = "HEAD") -> list[str]:
    result = _git(repo, "diff", "--name-only", base_ref, head)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def version_at(repo: Path, rev: str) -> str:
    result = _git(repo, "show", f"{rev}:pyproject.toml")
    return _version_from_pyproject(result.stdout)


def _print_errors(title: str, errors: list[str]) -> int:
    print(title, file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


def check_pr(repo: Path, base_ref: str, *, allow_major: bool) -> int:
    base_version = version_at(repo, base_ref)
    current_version = _version_from_pyproject((repo / "pyproject.toml").read_text(encoding="utf-8"))
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    paths = changed_paths(repo, base_ref, "HEAD")
    if base_version == current_version and is_skippable_change(paths):
        print("PR 只改了 .github/、tests/ 或 scripts/，跳过版本检查。")
        return 0
    errors = validate_version_change(base_version, current_version, changelog, allow_major=allow_major)
    if errors:
        _print_errors("PR 版本检查失败：", errors)
        print(
            "请按 AGENTS.md 选择一个版本级别，并在 CHANGELOG.md 添加对应版本条目。"
            "major 版本需维护者给 PR 添加 version:major 标签。",
            file=sys.stderr,
        )
        return 1
    print(f"PR 版本检查通过：{base_version} → {current_version}；CHANGELOG 条目存在。")
    return 0


def check_main(repo: Path, before: str) -> int:
    if not before or before == ZERO_SHA:
        print("没有可比较的推送前提交，跳过合并后版本复查。")
        return 0
    parent_version = version_at(repo, before)
    head_version = version_at(repo, "HEAD")
    changelog = _git(repo, "show", "HEAD:CHANGELOG.md").stdout
    paths = changed_paths(repo, before, "HEAD")
    errors = validate_main_advance(parent_version, head_version, paths, changelog)
    if errors:
        return _print_errors("合并后版本复查失败：", errors)
    if parent_version == head_version:
        print(f"合并后版本复查通过：{head_version} 未变化，改动在可跳过范围内。")
    else:
        print(f"合并后版本复查通过：{parent_version} → {head_version}。")
    return 0


def first_version_commits(repo: Path) -> list[tuple[str, str]]:
    """First-parent commits on HEAD, in history order, first time each version appears."""
    log = _git(repo, "rev-list", "--first-parent", "--reverse", "HEAD")
    seen: dict[str, str] = {}
    order: list[tuple[str, str]] = []
    for sha in log.stdout.split():
        try:
            version = version_at(repo, sha)
        except (subprocess.CalledProcessError, ValueError, tomllib.TOMLDecodeError):
            continue
        if parse_version(version) is None or version in seen:
            continue
        seen[version] = sha
        order.append((version, sha))
    return order


def tag_target(repo: Path, tag: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def create_missing_tags(repo: Path, *, push: bool) -> int:
    changelog = ""
    changelog_result = _git(repo, "show", "HEAD:CHANGELOG.md", check=False)
    if changelog_result.returncode == 0:
        changelog = changelog_result.stdout
    created: list[str] = []
    for version, sha in first_version_commits(repo):
        tag = f"v{version}"
        current = tag_target(repo, tag)
        if current == sha:
            continue
        if current is not None:
            print(f"tag {tag} 已指向 {current}，与版本首次出现的提交 {sha} 不一致。", file=sys.stderr)
            return 1
        section = changelog_version_section(changelog, version)
        message = f"my-slides {version}" if not section else f"my-slides {version}\n\n{section.strip()}\n"
        _git(repo, "tag", "-a", tag, sha, "-m", message)
        created.append(tag)
        print(f"已创建 {tag} → {sha}")
    if push and created:
        _git(repo, "push", "origin", *created)
        print("已推送：" + "、".join(created))
    elif not created:
        print("没有需要新建的版本 tag。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check-pr", "check-main", "tag"), default="check-pr")
    parser.add_argument("--base-ref", help="PR 目标分支的本地 ref，例如 origin/main")
    parser.add_argument("--before", help="推送到 main 之前的提交，用于合并后复查")
    parser.add_argument("--push", action="store_true", help="tag 模式：把新建的 tag 推送到 origin")
    parser.add_argument("--repo", type=Path, help="仓库根目录，默认是脚本所在仓库")
    args = parser.parse_args(argv)
    root = (args.repo or Path(__file__).resolve().parents[1]).resolve()
    try:
        if args.mode == "check-pr":
            if not args.base_ref:
                print("check-pr 需要 --base-ref", file=sys.stderr)
                return 2
            allow_major = os.environ.get("MY_SLIDES_ALLOW_MAJOR_VERSION", "").lower() == "true"
            return check_pr(root, args.base_ref, allow_major=allow_major)
        if args.mode == "check-main":
            return check_main(root, args.before or "")
        return create_missing_tags(root, push=args.push)
    except (OSError, subprocess.SubprocessError, tomllib.TOMLDecodeError, ValueError) as exc:
        print(f"版本检查无法运行：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
