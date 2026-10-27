"""Versioned thin workspace and honest, per-target presentation checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .command_output import emit
from .design_engine import design_status, run_agent
from .project import project_root

PROVIDERS = {"beautiful": "beautiful-article", "slides": "design-and-slides"}
DEFAULT = {"schema_version": 1, "article": "my-slides/article.md", "present": {}}


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _workspace(root: Path) -> Path:
    base = root.resolve() / "my-slides"
    if base.resolve() != base:
        raise ValueError(f"工作区路径越界或被链接重定向：{base}")
    return base


def _path(root: Path, value: str, *, output: bool) -> Path:
    if not isinstance(value, str) or not value or Path(value).anchor:
        raise ValueError(f"路径必须是相对项目根的非空路径：{value}")
    resolved = (root / value).resolve()
    boundary = _workspace(root) if output else root.resolve()
    if not _inside(resolved, boundary):
        raise ValueError(f"路径越界：{value}（边界：{boundary}）")
    return resolved


def read_project(root: Path) -> dict[str, Any]:
    path = _path(root, "my-slides/project.json", output=True)
    if not path.is_file():
        if (root / "my-slides" / "project.yaml").exists():
            raise ValueError("仅发现旧 project.yaml；请在旧项目复制件上添加 project.json，勿将旧审批视为新正文批准")
        raise ValueError(f"缺少 {path}；先运行 my-slides init")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"project.json 无效：{exc}") from exc
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ValueError("project.json 需要 schema_version: 1")
    article = _path(root, config.get("article"), output=False)
    if article == path:
        raise ValueError("article 不能指向 project.json")
    present = config.get("present")
    if not isinstance(present, dict) or set(present) - set(PROVIDERS):
        raise ValueError("present 必须是对象，且仅支持 beautiful、slides")
    outputs: list[Path] = []
    for name, entry in present.items():
        if not isinstance(entry, dict) or entry.get("provider") != PROVIDERS[name]:
            raise ValueError(f"{name}.provider 必须是 {PROVIDERS[name]}")
        out = _path(root, entry.get("output"), output=True)
        if (_inside(out, article) or _inside(article, out) or
                _inside(out, path) or _inside(path, out) or
                any(_inside(out, old) or _inside(old, out) for old in outputs)):
            raise ValueError(f"{name}.output 与输入或其他目标重叠")
        if name == "slides" and out.name != "deck":
            raise ValueError("slides.output 首版须以 deck 结尾，以便 Design 宿主定位")
        outputs.append(out)
    config["_article_path"] = article
    return config


def init(args: argparse.Namespace) -> int:
    if getattr(args, "legacy", False):
        from .commands.init import init_project
        return init_project(args)
    if getattr(args, "force", False) or getattr(args, "source_dir", None):
        raise ValueError("--force 和 --source-dir 仅适用于 init --legacy；薄壳不覆盖现有配置")
    root = project_root(args.project, discover=False)
    base = _workspace(root)
    target = base / "project.json"
    if target.exists() or target.is_symlink():
        raise ValueError(f"配置已存在，未覆盖：{target}")
    if (base / "project.yaml").exists():
        raise ValueError("发现旧 project.yaml；请先复制旧项目并按 docs/remake-contract.md 迁移")
    base.mkdir(exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(DEFAULT, ensure_ascii=False, indent=2) + "\n")
    emit(args, {"project": str(root), "config": str(target), "schema_version": 1}, f"已创建 {target}；请写入正文并选择呈现目标")
    return 0


def _fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    files = []
    for child in path.rglob("*"):
        if child.is_symlink() or child.resolve() != child:
            raise ValueError(f"产物目录含链接或越界路径：{child}")
        if child.is_file():
            files.append(child)
    digest = hashlib.sha256()
    for file in sorted(files):
        digest.update(file.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def present(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    config = read_project(root)
    targets = [args.target] if args.target else list(config["present"])
    if not targets:
        raise ValueError("尚未选择呈现目标；在 project.json 的 present 中添加 beautiful 和/或 slides")
    if any(name not in config["present"] for name in targets):
        raise ValueError("指定目标未在 project.json 启用")
    article = config["_article_path"]
    article_hash = None
    article_error = f"请先写非空 UTF-8 正文：{article}"
    try:
        if article.is_file():
            data = article.read_bytes()
            if data.decode("utf-8-sig").strip():
                article_hash = hashlib.sha256(data).hexdigest()
    except (OSError, ValueError) as exc:
        article_error = f"无法读取正文 {article}：{exc}"
    results: dict[str, Any] = {}
    for name in targets:
        entry = config["present"][name]
        result: dict[str, Any] = {"status": "pending_agent", "provider": entry["provider"], "output": entry["output"],
                                  "article_sha256": article_hash, "output_sha256": None,
                                  "content_sync": "unknown", "check": "not_run",
                                  "render": "not_run", "human_review": "not_done"}
        try:
            output = _path(root, entry["output"], output=True)
            result["output"] = str(output)
            result["output_sha256"] = _fingerprint(output)
            if not article_hash:
                result.update(status="failed", next=article_error)
            elif name == "beautiful":
                result["next"] = f"当前 Agent 阅读 beautiful-article skill，以 {article} 为输入制作 {output}；保留已有文件和手改。完成后人工核对内容与引用。"
            else:
                status = design_status()
                if not status["ready"]:
                    result.update(status="failed", next=f"Design 不可用；检查 {status['env']}、Node、安装和构建。Agent 再用 {article} 创作 {output}。")
                elif not (output / "deck.json").is_file():
                    result["next"] = f"当前 Agent 阅读 Design slides skill，用 {article} 在 {output} 创作 deck；宿主 projects 根为 {output.parent}，在线修改经 apply。"
                else:
                    code, check = run_agent(["check", "deck", "--strict"], output.parent)
                    result["check"] = check
                    if code == 0:
                        result.update(status="succeeded", completion="structure_check_only", next=f"Agent 先核对 {article} 与当前 deck 的内容一致性，再在 5173 渲染并由用户审阅；结构通过不等于内容已同步或视觉认可。")
                    else:
                        result.update(status="failed", next="Design strict 检查失败；修复后仅重试 slides。")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result.update(status="failed", next=f"{name} 检查失败：{exc}；保留现有产物，修复后仅重试此目标。")
        results[name] = result
    complete = all(item["status"] == "succeeded" for item in results.values())
    emit(args, {"complete": complete, "completion_scope": "deterministic_checks_only", "targets": results}, json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if complete else 1
