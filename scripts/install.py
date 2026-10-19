#!/usr/bin/env python3
"""Install the bundled Claude or Codex agents and skills."""

import argparse
import filecmp
import json
import os
from pathlib import Path
import re
import shutil
import sys


class InstallError(Exception):
    pass


# Token-efficient mode: only these agents' model and effort lines change.
ECO_AGENTS = {
    "claude": {
        "ai-planner.md": ("claude-opus-5-5", "high"),
        "ai-reviewer.md": ("claude-opus-5-5", "xhigh"),
        "ai-red-team.md": ("claude-opus-5-5", "xhigh"),
        "ai-builder.md": ("claude-opus-5-5", "medium"),
        "ai-loop.md": ("claude-opus-5-5", "low"),
        "ai-runner.md": ("claude-sonnet-5-5", "low"),
    },
    "codex": {
        "ai-planner.toml": ("gpt-6-sol", "high"),
        "ai-reviewer.toml": ("gpt-6-sol", "xhigh"),
        "ai-red-team.toml": ("gpt-6-sol", "xhigh"),
        "ai-builder.toml": ("gpt-6-sol", "medium"),
        "ai-loop.toml": ("gpt-6-sol", "low"),
        "ai-runner.toml": ("gpt-6-luna", "medium"),
    },
}

MODEL_LINES = {
    "claude": (r"^model:.*$", "model: {}", r"^effort:.*$", "effort: {}"),
    "codex": (
        r"^model\s*=.*$",
        'model = "{}"',
        r"^model_reasoning_effort\s*=.*$",
        'model_reasoning_effort = "{}"',
    ),
}


def eco_contents(source, runtime):
    """Return the agent file with eco model/effort lines, or None to copy as is."""
    setting = ECO_AGENTS[runtime].get(source.name)
    if setting is None:
        return None
    text = source.read_text(encoding="utf-8")
    model_pattern, model_line, effort_pattern, effort_line = MODEL_LINES[runtime]
    for pattern, line, value in (
        (model_pattern, model_line, setting[0]),
        (effort_pattern, effort_line, setting[1]),
    ):
        text, count = re.subn(
            pattern, lambda _: line.format(value), text, count=1, flags=re.MULTILINE
        )
        if count != 1:
            raise InstallError(f"cannot find {pattern!r} for eco mode in {source}")
    return text.encode("utf-8")


def safe_path(path):
    """Return an absolute path after rejecting traversal and symlink components."""
    path = Path(path).expanduser()
    if ".." in path.parts:
        raise InstallError(f"unsafe path traversal: {path}")
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise InstallError(f"symlink path component is not allowed: {current}")
    return path


def require_directory(path, label):
    path = safe_path(path)
    if not path.is_dir():
        raise InstallError(f"missing {label} directory: {path}")
    return path


def source_files(source, destination):
    """Build copy pairs while refusing links and non-regular bundle entries."""
    pairs = []
    for root, directories, filenames in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name != "__pycache__"]
        root_path = Path(root)
        for name in directories:
            candidate = root_path / name
            if candidate.is_symlink():
                raise InstallError(f"bundle contains a symlink: {candidate}")
        for name in filenames:
            if name == ".DS_Store" or name.endswith(".pyc"):
                continue
            candidate = root_path / name
            if candidate.is_symlink() or not candidate.is_file():
                raise InstallError(f"bundle entry is not a regular file: {candidate}")
            relative = candidate.relative_to(source)
            if ".." in relative.parts:
                raise InstallError(f"unsafe bundle path: {candidate}")
            pairs.append((candidate, destination / relative))
    return pairs


def check_destination(path):
    path = safe_path(path)
    current = Path(path.anchor)
    for part in path.parts[1:-1]:
        current /= part
        if current.exists() and not current.is_dir():
            raise InstallError(f"destination parent is not a directory: {current}")
    return path


def load_json(path, label):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f"cannot read {label} JSON at {path}: {error}") from error
    if not isinstance(value, dict):
        raise InstallError(f"{label} JSON must contain an object: {path}")
    return value


def merged_settings(bundle_root, settings_path):
    hook_path = safe_path(bundle_root / "hooks" / "compact-reminder.json")
    if not hook_path.is_file():
        raise InstallError(f"missing hook file: {hook_path}")
    hook_config = load_json(hook_path, "hook")
    hook_groups = hook_config.get("hooks")
    handlers = hook_groups.get("SessionStart") if isinstance(hook_groups, dict) else None
    if not isinstance(handlers, list):
        raise InstallError(f"hook JSON must contain hooks.SessionStart list: {hook_path}")

    if settings_path.exists():
        settings = load_json(settings_path, "Claude settings")
    else:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"Claude settings hooks must be an object: {settings_path}")
    existing = hooks.setdefault("SessionStart", [])
    if not isinstance(existing, list):
        raise InstallError(
            f"Claude settings hooks.SessionStart must be a list: {settings_path}"
        )
    for handler in handlers:
        if handler not in existing:
            existing.append(handler)
    return settings


def destinations(args):
    if args.project is not None:
        base = safe_path(args.project)
        if args.runtime == "claude":
            return base / ".claude" / "agents", base / ".claude" / "skills"
        return base / ".codex" / "agents", base / ".agents" / "skills"

    home = safe_path(os.environ.get("HOME", str(Path.home())))
    if args.runtime == "claude":
        claude_home = safe_path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
        return claude_home / "agents", claude_home / "skills"
    codex_home = safe_path(os.environ.get("CODEX_HOME") or home / ".codex")
    return codex_home / "agents", home / ".agents" / "skills"


def install(args):
    package_root = safe_path(Path(__file__).parent.parent)
    agents_dest, skills_dest = destinations(args)
    pairs = []
    agent_sources = []
    if args.package in ("operations", "all"):
        bundle_root = require_directory(package_root / args.runtime, args.runtime + " bundle")
        agent_sources.append(require_directory(bundle_root / "agents", "agents"))
        pairs += source_files(require_directory(bundle_root / "skills", "skills"), skills_dest)
        pairs += source_files(
            require_directory(package_root / "evaluation-loop" / "skills", "evaluation loop"),
            skills_dest,
        )
    if args.package in ("red-team", "all"):
        red_root = package_root / "red-team"
        agent_sources.append(
            require_directory(red_root / args.runtime / "agents", "red-team agents")
        )
        pairs += source_files(require_directory(red_root / "skills", "red-team skill"), skills_dest)
    entries = [
        (source, destination, eco_contents(source, args.runtime) if args.mode == "eco" else None)
        for root in agent_sources
        for source, destination in source_files(root, agents_dest)
    ]
    entries += [(source, destination, None) for source, destination in pairs]
    pending = []
    for source, raw_destination, contents in entries:
        destination = check_destination(raw_destination)
        if destination.exists():
            if contents is None:
                same = destination.is_file() and filecmp.cmp(source, destination, shallow=False)
            else:
                same = destination.is_file() and destination.read_bytes() == contents
            if not same:
                raise InstallError(
                    f"collision at {destination}; move or remove the existing file and retry"
                )
        else:
            pending.append((source, destination, contents))

    settings_update = None
    if args.with_context_hook:
        settings_path = check_destination(agents_dest.parent / "settings.json")
        settings = merged_settings(bundle_root, settings_path)
        rendered = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
        if not settings_path.exists() or settings_path.read_text(encoding="utf-8") != rendered:
            settings_update = (settings_path, rendered)

    roots = sorted({agents_dest, skills_dest}, key=str)
    if args.dry_run:
        print(f"mode: {args.mode}")
        for root in roots:
            print(f"would install: {root}")
        if settings_update:
            print(f"would update: {settings_update[0]}")
        return

    for source, destination, contents in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if contents is None:
            shutil.copy2(source, destination)
        else:
            destination.write_bytes(contents)
            shutil.copystat(source, destination)
    if settings_update:
        path, contents = settings_update
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    for root in roots:
        print(f"installed: {root}")
    if settings_update:
        print(f"updated: {settings_update[0]}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", choices=("claude", "codex"))
    parser.add_argument("--package", choices=("operations", "red-team", "all"), default="operations")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", metavar="PATH")
    target.add_argument("--user", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("standard", "eco"),
        default="standard",
        help="eco swaps agent model/effort lines for token-efficient defaults",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--with-context-hook",
        action="store_true",
        help="merge the optional Claude context reminder hook",
    )
    args = parser.parse_args()
    if args.with_context_hook and args.runtime != "claude":
        parser.error("--with-context-hook is available only for claude")
    if args.with_context_hook and args.package == "red-team":
        parser.error("--with-context-hook requires the operations package")
    return args


def main():
    try:
        install(parse_args())
    except InstallError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
