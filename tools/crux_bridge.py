"""CRUX Bridge -- persistent JSON-line stdin/stdout protocol for VS Code extension.

Protocol (one JSON object per line):
    Input:  {"id":"1", "method":"chat",    "params":{"prompt":"...", "files":[...]}}
    Input:  {"id":"2", "method":"reset"}
    Input:  {"id":"3", "method":"quit"}

    Output: {"id":"1", "type":"text",       "content":"Hello"}
    Output: {"id":"1", "type":"tool_start", "content":"", "tool":"read_file", "message":"reading core/chat.py"}
    Output: {"id":"1", "type":"tool_end",   "content":"", "tool":"read_file", "success":true}
    Output: {"id":"1", "type":"info",       "content":"..."}
    Output: {"id":"1", "type":"error",      "content":"..."}
    Output: {"id":"1", "type":"done",       "content":""}

The process stays alive across multiple chat calls, maintaining conversation history.
Agent mode is enabled so the model can call tools (read/write/search/run).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import traceback
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="[bridge] %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("crux_bridge")

# ── Tool activity patterns ──────────────────────────────────────

_TOOL_PATTERNS = [
    (re.compile(r"读取\s+(.+)"), "read_file"),
    (re.compile(r"read(?:ing)?\s+(.+)", re.IGNORECASE), "read_file"),
    (re.compile(r"写入\s+(.+)"), "write_file"),
    (re.compile(r"编[辑辑]\s+(.+)"), "edit_file"),
    (re.compile(r"writ(?:e|ing)\s+(.+)", re.IGNORECASE), "write_file"),
    (re.compile(r"edit(?:ing)?\s+(.+)", re.IGNORECASE), "edit_file"),
    (re.compile(r"搜索\s+(.+)"), "search_files"),
    (re.compile(r"search(?:ing)?\s+(.+)", re.IGNORECASE), "search_files"),
    (re.compile(r"执行\s+(.+)"), "run_bash"),
    (re.compile(r"run(?:ning)?\s+(.+)", re.IGNORECASE), "run_bash"),
    (re.compile(r"测试\s+(.+)"), "run_test"),
    (re.compile(r"test(?:ing)?\s+(.+)", re.IGNORECASE), "run_test"),
    (re.compile(r"审查\s+(.+)"), "code_review"),
    (re.compile(r"review(?:ing)?\s+(.+)", re.IGNORECASE), "code_review"),
    (re.compile(r"globb?ing\s+(.+)", re.IGNORECASE), "glob_files"),
    (re.compile(r"find(?:ing)?\s+(.+)", re.IGNORECASE), "glob_files"),
    (re.compile(r"列出\s+(.+)"), "list_files"),
    (re.compile(r"list(?:ing)?\s+(.+)", re.IGNORECASE), "list_files"),
    (re.compile(r"git\s+(.+)"), "git"),
    (re.compile(r"agent.*swarm", re.IGNORECASE), "agent_swarm"),
    (re.compile(r"multi.*agent", re.IGNORECASE), "multi_agent"),
]


def _parse_tool_activity(text: str) -> tuple[str, str] | None:
    for pattern, tool_name in _TOOL_PATTERNS:
        m = pattern.search(text)
        if m:
            detail = m.group(1).strip().rstrip(".")
            return (tool_name, f"{tool_name}: {detail}")
    return None


def emit(msg_id: str, type_: str, content: str = "", **extra) -> None:
    payload = {"id": msg_id, "type": type_, "content": content}
    payload.update(extra)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def build_context_prefix(files: list[dict] | None) -> str:
    if not files:
        return ""
    parts = ["[Context files]\n"]
    for f in files:
        path = f.get("path", "unknown")
        content = f.get("content", "")
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        max_len = 8000
        if len(content) > max_len:
            content = content[:max_len] + f"\n... (truncated, {len(content)} chars total)"
        parts.append(f"File: {path}\n```{ext}\n{content}\n```\n")
    parts.append("User: ")
    return "".join(parts)


def create_session() -> Any:
    from core.chat import ChatSession
    from core.provider import get_provider_manager

    mgr = get_provider_manager()
    client = mgr.create_client()
    model = mgr.get_model("light") or "deepseek-v4-flash"
    session = ChatSession(client=client, default_model=model)
    session.agent_mode = True
    logger.info("Session created with model=%s agent_mode=True", model)
    return session


def handle_chat(session: Any, msg_id: str, params: dict) -> None:
    prompt = params.get("prompt", "")
    files = params.get("files")

    if not prompt:
        emit(msg_id, "error", "Missing 'prompt' field")
        emit(msg_id, "done", "")
        return

    context_prefix = build_context_prefix(files)
    full_prompt = context_prefix + prompt

    active_tool: str | None = None

    try:
        for kind, payload in session.send_stream(full_prompt):
            if kind == "text" and payload:
                text = str(payload)

                if text.startswith("\n> "):
                    activity = text[3:].strip()
                    parsed = _parse_tool_activity(activity)
                    if parsed:
                        tool_name, message = parsed
                        active_tool = tool_name
                        emit(msg_id, "tool_start", "", tool=tool_name, message=message)
                    emit(msg_id, "text", text)

                elif active_tool and "\n> " not in text:
                    emit(msg_id, "tool_end", "", tool=active_tool, success=True)
                    active_tool = None
                    emit(msg_id, "text", text)

                else:
                    emit(msg_id, "text", text)

            elif kind == "tool_result" and payload:
                if isinstance(payload, dict):
                    tname = payload.get("name", "")
                    if active_tool and tname and tname != active_tool:
                        emit(msg_id, "tool_end", "", tool=active_tool, success=True)
                        active_tool = tname
                if active_tool:
                    emit(msg_id, "tool_end", "", tool=active_tool, success=True)
                    active_tool = None

            elif kind == "info" and payload:
                emit(msg_id, "info", str(payload))

            elif kind == "error":
                emit(msg_id, "error", str(payload))

            # Skip image/video/confirm types for VS Code panel

        if active_tool:
            emit(msg_id, "tool_end", "", tool=active_tool, success=True)

        emit(msg_id, "done", "")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Chat error: %s\n%s", e, tb)
        if active_tool:
            emit(msg_id, "tool_end", "", tool=active_tool, success=False)
        emit(msg_id, "error", f"{type(e).__name__}: {e}")
        emit(msg_id, "done", "")


def handle_reset(session: Any, msg_id: str) -> None:
    if session is None:
        emit(msg_id, "error", "Session not initialized")
        emit(msg_id, "done", "")
        return
    try:
        session.reset()
        emit(msg_id, "info", "Conversation reset")
        emit(msg_id, "done", "")
    except Exception as e:
        emit(msg_id, "error", f"Reset failed: {e}")
        emit(msg_id, "done", "")


def main() -> None:
    logger.info("Bridge starting, creating session...")
    try:
        session = create_session()
    except Exception as e:
        logger.error("Failed to create initial session: %s", e)
        session = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON input: %s", e)
            emit("", "error", f"Invalid JSON: {e}")
            continue

        msg_id = data.get("id", "")
        method = data.get("method", "")
        params = data.get("params", {})

        if method == "quit":
            logger.info("Bridge quitting")
            emit(msg_id, "done", "")
            break

        if method == "reset":
            handle_reset(session, msg_id)
            continue

        if method == "chat":
            if session is None:
                try:
                    session = create_session()
                except Exception as e:
                    emit(msg_id, "error", f"Session init failed: {e}")
                    emit(msg_id, "done", "")
                    continue
            handle_chat(session, msg_id, params)
            continue

        emit(msg_id, "error", f"Unknown method: {method}")
        emit(msg_id, "done", "")

    logger.info("Bridge exited")


if __name__ == "__main__":
    main()
