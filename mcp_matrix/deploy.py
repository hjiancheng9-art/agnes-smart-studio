#!/usr/bin/env python3
"""
MCP Matrix Deployment Script
=============================
Deploy MCP interconnections: Claude Code ↔ Codex ↔ Kimi Code ↔ CodeBuddy ↔ ZCode/CRUX

Usage:
  python mcp_matrix/deploy.py           # Deploy all configs
  python mcp_matrix/deploy.py --dry-run # Show what would be done
  python mcp_matrix/deploy.py --tool claude-code  # Deploy for specific tool
"""

import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
PYTHON_EXE = sys.executable  # Use current Python
BRIDGE_DIR = PROJECT_ROOT / "core" / "mcp_servers"

# ── Bridge scripts ──
BRIDGES = {
    "claude-code": BRIDGE_DIR / "claude_code_bridge.py",
    "codex":       BRIDGE_DIR / "codex_bridge.py",
    "kimi":        BRIDGE_DIR / "kimi_bridge.py",
    "codebuddy":   BRIDGE_DIR / "codebuddy_bridge.py",
    "zcode":       BRIDGE_DIR / "crux_mcp_entry.py",
}

CRUX_STUDIO = PROJECT_ROOT / "crux_studio.py"


def entry(bridge_name: str) -> dict:
    """Create an MCP server entry for a bridge."""
    return {"command": PYTHON_EXE, "args": [str(BRIDGES[bridge_name])]}


# ── Deployers ──

def deploy_claude_code(dry_run=False):
    """~/.claude/.mcp.json"""
    target = HOME / ".claude" / ".mcp.json"
    config = {
        "mcpServers": {
            "codex":     entry("codex"),
            "kimi":      entry("kimi"),
            "codebuddy": entry("codebuddy"),
            "zcode":     entry("zcode"),
            "crux": {
                "command": PYTHON_EXE,
                "args": [str(CRUX_STUDIO), "mcp-serve"],
            },
        }
    }
    _write_json(target, config, dry_run)


def deploy_codex(dry_run=False):
    """~/.codex/config.toml — append [mcp_servers.*] entries."""
    target = HOME / ".codex" / "config.toml"
    entries = []
    for name in ["claude-code", "kimi", "codebuddy", "zcode"]:
        bp = BRIDGES[name]
        entries.append(f'\n[mcp_servers.{name}]')
        entries.append(f'command = "{PYTHON_EXE}"')
        entries.append(f'args = ["{bp.as_posix()}"]')

    block = "\n".join(entries)
    marker = "# === MCP MATRIX ==="

    if dry_run:
        print(f"[DRY RUN] Would append to {target}:\n{marker}\n{block}")
        return

    if not target.exists():
        print(f"  ✗ {target} not found — skipping Codex")
        return

    content = target.read_text(encoding="utf-8")
    if marker in content:
        content = content[: content.index(marker)].rstrip()

    new_content = content.rstrip() + f"\n\n{marker}\n{block}\n"
    _backup_write(target, new_content)


def deploy_codebuddy(dry_run=False):
    """~/.codebuddy/mcp.json"""
    target = HOME / ".codebuddy" / "mcp.json"
    config = {"mcpServers": {n: entry(n) for n in ["claude-code", "codex", "kimi", "zcode"]}}
    _write_json(target, config, dry_run)


def deploy_kimi(dry_run=False):
    """~/.kimi/mcp.json"""
    target = HOME / ".kimi" / "mcp.json"
    config = {"mcpServers": {n: entry(n) for n in ["claude-code", "codex", "codebuddy", "zcode"]}}
    _write_json(target, config, dry_run)


# ── Helpers ──

def _write_json(target, config, dry_run):
    text = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if dry_run:
        print(f"[DRY RUN] Would write {target}:\n{text}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    _backup_write(target, text)


def _backup_write(target, text):
    if target.exists():
        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, bak)
        print(f"  Backed up → {bak.name}")
    target.write_text(text, encoding="utf-8")
    print(f"  ✓ {target}")


# ── Main ──

def main():
    dry_run = "--dry-run" in sys.argv
    specific = next((a.split("=",1)[1] for a in sys.argv if a.startswith("--tool=")), None)

    print("=" * 60)
    print("MCP Matrix: Claude Code ↔ Codex ↔ Kimi ↔ CodeBuddy ↔ ZCode")
    print(f"Mode: {'DRY RUN' if dry_run else 'DEPLOY'}")
    print("=" * 60)

    # Verify bridges
    missing = [n for n, p in BRIDGES.items() if not p.exists()]
    if missing:
        print(f"\n✗ Missing bridges: {missing}")
        print("  Run from agnes-smart-studio/ project root.")
        return 1
    print("\n✓ All bridge scripts found")

    deployers = [
        ("Claude Code", deploy_claude_code),
        ("Codex",       deploy_codex),
        ("Kimi Code",   deploy_kimi),
        ("CodeBuddy",   deploy_codebuddy),
    ]

    for label, fn in deployers:
        if specific and specific not in label.lower():
            continue
        print(f"\n── {label} ──")
        try:
            fn(dry_run=dry_run)
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("\n" + "=" * 60)
    print("Done! Restart tools to activate." if not dry_run else "Dry run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
