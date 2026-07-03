"""Thin display helpers for CLI tools — system viewer, plan updates, search, user input."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _view_image(path: str) -> str:
    """Open image with system default viewer. Supports PNG, JPG, GIF, WebP, SVG."""
    p = Path(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"}, ensure_ascii=False)
    try:
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            subprocess.run(["xdg-open", str(p)], check=False)
        return json.dumps({"opened": str(p)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _update_plan(
    action: str = "",
    step_id: int = 0,
    name: str = "",
    tool: str = "",
    args: dict | None = None,
    reason: str = "",
) -> str:
    """Update the current execution plan mid-task — add, remove, modify, or insert a step."""
    try:
        from core.plan_mode import PlanManager
        mgr = PlanManager()
        if action == "add":
            mgr.add_step(name=name, tool=tool, args=args or {})
        elif action == "remove":
            mgr.remove_step(step_id)
        elif action == "modify":
            mgr.modify_step(step_id, name=name, tool=tool, args=args or {})
        elif action == "insert":
            mgr.insert_step(step_id, name=name, tool=tool, args=args or {})
        else:
            return json.dumps({"error": f"Unknown action: {action}. Use add/remove/modify/insert."}, ensure_ascii=False)
        return json.dumps({"status": "ok", "action": action, "reason": reason}, ensure_ascii=False)
    except ImportError:
        return json.dumps({"status": "ok", "note": "Plan mode not active — command accepted"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tool_search(query: str) -> str:
    """Search available tools by keyword. Returns matching tool names and descriptions."""
    try:
        tools_path = Path(__file__).resolve().parent.parent / "tools.json"
        data = json.loads(tools_path.read_text(encoding="utf-8"))
        matches = []
        q = query.lower()
        for t in data.get("tools", []):
            name = t.get("name", "")
            desc = t.get("description", "")
            if q in name.lower() or q in desc.lower():
                matches.append({"name": name, "description": desc[:120]})
        if not matches:
            return json.dumps({"query": query, "matches": [], "hint": "No matching tools found"}, ensure_ascii=False)
        return json.dumps({"query": query, "matches": matches[:20]}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _request_user_input(question: str) -> str:
    """Ask the user a question and wait for typed response. Returns the answer text."""
    try:
        answer = input(f"\n  ? {question}\n  > ")
        return json.dumps({"question": question, "answer": answer}, ensure_ascii=False)
    except (EOFError, KeyboardInterrupt):
        return json.dumps({"question": question, "answer": "", "cancelled": True}, ensure_ascii=False)
