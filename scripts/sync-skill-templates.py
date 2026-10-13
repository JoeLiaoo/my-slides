#!/usr/bin/env python3
"""Mirror ``skills/my-slides-workflow/{references,examples}`` to the wheel install.

The repository copy under ``skills/my-slides-workflow/`` is the only place where
skill text is edited.  The packaged wheel exposes the same content under
``src/my_slides/templates/{references,examples}`` so that installed projects
have the references and example library without having to clone the repo.

This script:

* copies ``SKILL.md`` to ``templates/my-slides-workflow.md``;
* copies each file under ``references/`` to ``templates/references/``;
* copies each file under ``examples/`` (including ``examples/index/``) to
  ``templates/examples/``;
* rejects the operation if the destination has changes that are not in the
  source (or vice versa) — pass ``--force`` to overwrite;
* can also be used to check that both copies are still in step (``--check``).

The script is intentionally small and dependency-free so it can run in CI and
inside the package build.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import shutil
import sys
from pathlib import Path

SKILL_DIR = "my-slides-workflow"
SKILL_FILE = "SKILL.md"
PACKAGED_SKILL_FILE = "my-slides-workflow.md"

# Subtrees that mirror verbatim.  Anything else under skills/ is not synced.
MIRRORED_DIRS: tuple[str, ...] = ("references", "examples")


def _repo_root(start: Path) -> Path:
    return start.resolve().parents[1]


def _mirror_paths(repo: Path) -> tuple[Path, Path]:
    source = repo / "skills" / SKILL_DIR
    destination = repo / "src" / "my_slides" / "templates"
    if not source.is_dir():
        raise SystemExit(f"missing skill directory: {source}")
    if not destination.is_dir():
        raise SystemExit(f"missing template directory: {destination}")
    return source, destination


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_files(root: Path) -> dict[str, Path]:
    """Return ``{relative_posix_path: absolute_path}`` for every file under ``root``."""
    found: dict[str, Path] = {}
    for item in root.rglob("*"):
        if item.is_file():
            found[item.relative_to(root).as_posix()] = item
    return found


def _diff(source_files: dict[str, Path], dest_files: dict[str, Path]) -> dict[str, list[str]]:
    """Return mapping ``{status: [relative paths]}`` between two file dicts."""
    only_source = sorted(set(source_files) - set(dest_files))
    only_dest = sorted(set(dest_files) - set(source_files))
    common = sorted(set(source_files) & set(dest_files))
    drift: list[str] = []
    for relative in common:
        if _hash(source_files[relative]) != _hash(dest_files[relative]):
            drift.append(relative)
    return {
        "only_source": only_source,
        "only_dest": only_dest,
        "drift": drift,
    }


def _format_report(diff: dict[str, list[str]]) -> str:
    parts: list[str] = []
    if diff["only_source"]:
        parts.append("only in source: " + ", ".join(diff["only_source"]))
    if diff["only_dest"]:
        parts.append("only in destination: " + ", ".join(diff["only_dest"]))
    if diff["drift"]:
        parts.append("content drift: " + ", ".join(diff["drift"]))
    return "; ".join(parts) if parts else "in sync"


def sync(repo: Path, *, force: bool = False, check: bool = False) -> int:
    source, destination = _mirror_paths(repo)
    errors: list[str] = []

    skill_md = source / SKILL_FILE
    if not skill_md.is_file():
        errors.append(f"missing {skill_md}")
    packaged = destination / PACKAGED_SKILL_FILE
    if not packaged.is_file():
        errors.append(f"missing {packaged}")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    payload = filecmp.cmp(skill_md, packaged, shallow=False)
    if not payload:
        if check:
            print(
                f"skill text drift: {skill_md.relative_to(repo)} != {packaged.relative_to(repo)}",
                file=sys.stderr,
            )
            return 2
        if not force:
            print(
                "refusing to overwrite packaged skill text; rerun with --force",
                file=sys.stderr,
            )
            return 3
        shutil.copyfile(skill_md, packaged)
        print(f"synced {skill_md.relative_to(repo)} → {packaged.relative_to(repo)}")

    for sub in MIRRORED_DIRS:
        src_root = source / sub
        dst_root = destination / sub
        src_files = _relative_files(src_root)
        if not dst_root.is_dir():
            errors.append(f"missing {dst_root}")
            continue
        dst_files = _relative_files(dst_root)
        diff = _diff(src_files, dst_files)
        if any(diff.values()):
            if check:
                print(
                    f"{sub}/ drift: {_format_report(diff)}",
                    file=sys.stderr,
                )
                errors.append("drift detected")
                continue
            if not force:
                print(
                    f"{sub}/ out of sync ({_format_report(diff)}); rerun with --force",
                    file=sys.stderr,
                )
                return 3
        if check:
            continue
        for relative, src_path in src_files.items():
            dst_path = dst_root / relative
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if dst_path.is_file() and _hash(src_path) == _hash(dst_path):
                continue
            shutil.copyfile(src_path, dst_path)
            print(f"synced {sub}/{relative}")
        for relative in diff["only_dest"]:
            (dst_root / relative).unlink(missing_ok=True)
            print(f"removed extra {sub}/{relative}")

    if check and errors:
        return 2
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    if not check:
        print("templates/ mirrors skills/my-slides-workflow/")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite drift between the source and destination",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if source and destination are not in step",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=_repo_root(Path(__file__).resolve()),
        help="repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)
    return sync(args.repo, force=args.force, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
