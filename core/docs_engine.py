"""Real-time documentation engine — generates docs from live code state."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _count_tests() -> int:
    tests_dir = ROOT / "tests"
    return len([f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")])


def _count_core_modules() -> int:
    return len([f for f in os.listdir(ROOT / "core") if f.endswith(".py") and not f.startswith("_")])


def _count_skills() -> int:
    skills_dir = ROOT / "skills"
    if skills_dir.exists():
        return len([f for f in os.listdir(skills_dir) if f.endswith(".skill.json")])
    return 0


def sync_manifest() -> dict:
    """Sync crux_manifest.json stats from live state."""
    manifest_path = ROOT / "crux_manifest.json"
    if not manifest_path.exists():
        return {"error": "manifest not found"}

    from core.commands import COMMANDS

    with open(ROOT / "tools.json", encoding="utf-8") as f:
        tools_data = json.load(f)
    tool_count = len(tools_data.get("tools", tools_data if isinstance(tools_data, list) else []))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stats"]["commands"] = len(COMMANDS)
    manifest["stats"]["tools"] = tool_count
    manifest["stats"]["skills_local"] = _count_skills()

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest["stats"]


def sync_agents_md() -> str:
    """Update dynamic sections of AGENTS.md."""
    path = ROOT / "AGENTS.md"
    if not path.exists():
        return "AGENTS.md not found"

    content = path.read_text(encoding="utf-8")
    from core.commands import COMMANDS

    with open(ROOT / "tools.json", encoding="utf-8") as f:
        tools_data = json.load(f)
    tool_count = len(tools_data.get("tools", tools_data if isinstance(tools_data, list) else []))

    # Update snapshot section counts
    content = re.sub(
        r"(\d+) commands, (\d+) tools, (\d+) local skills",
        f"{len(COMMANDS)} commands, {tool_count} tools, {_count_skills()} local skills",
        content,
    )
    content = re.sub(
        r"Core modules: (\d+) \.py files",
        f"Core modules: {_count_core_modules()} .py files",
        content,
    )

    path.write_text(content, encoding="utf-8")
    return f"AGENTS.md synced ({len(COMMANDS)} commands, {tool_count} tools, {_count_skills()} skills, {_count_core_modules()} modules)"


def render_help_md() -> str:
    """Render the HELP.md command reference from the live COMMANDS registry.

    Pure function: no filesystem writes, deterministic output. Category order
    follows COMMANDS insertion order (get_by_category preserves it). Use this
    for drift checks; use generate_help_md() to also write the file.
    """
    from core.commands import COMMANDS, get_by_category

    cats = get_by_category()
    lines = ["# CRUX Studio — 命令参考 (auto-generated)", "", f"共 {len(COMMANDS)} 个命令", ""]

    for cat, cmds in cats.items():
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| 命令 | 说明 |")
        lines.append("|------|------|")
        for name, args_hint, desc, _ in cmds:
            arg = f" {args_hint}" if args_hint else ""
            lines.append(f"| `{name}{arg}` | {desc} |")
        lines.append("")

    # Tool count from tools.json
    with open(ROOT / "tools.json", encoding="utf-8") as f:
        tools_data = json.load(f)
    tool_count = len(tools_data.get("tools", tools_data if isinstance(tools_data, list) else []))
    lines.append("---")
    lines.append(
        f"*{tool_count} tools, {_count_skills()} skills, {_count_core_modules()} core modules, {_count_tests()} test files*"
    )
    return "\n".join(lines)


def generate_help_md() -> str:
    """Render HELP.md and write it to disk. Returns a short status string."""
    from core.commands import COMMANDS

    result = render_help_md()
    (ROOT / "HELP.md").write_text(result, encoding="utf-8")
    with open(ROOT / "tools.json", encoding="utf-8") as f:
        tools_data = json.load(f)
    tool_count = len(tools_data.get("tools", tools_data if isinstance(tools_data, list) else []))
    return f"HELP.md generated ({len(COMMANDS)} commands, {tool_count} tools)"


def generate_all() -> dict:
    """Run all documentation generation."""
    return {
        "manifest": sync_manifest(),
        "agents_md": sync_agents_md(),
        "help_md": generate_help_md(),
    }
