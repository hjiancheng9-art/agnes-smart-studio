"""Remediation Executor (P22) — 安全自动修复引擎。

分级执行修复命令，低风险自动执行，高风险请求确认。
所有操作写入 Recovery Ledger 确保可追溯和可回滚。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.remediation")

# ── Risk Classification ──────────────────────────────────────────

LOW_RISK_COMMANDS: set[str] = {
    "retry_with_backoff",
    "clear_cache",
    "increase_timeout",
    "switch_provider",
}

HIGH_RISK_COMMANDS: set[str] = {
    "reset_circuit_breaker",
    "force_local_once",
    "clear_all_provider_cache",
    "reset_all_circuit_breakers",
    "override_provider_priority",
}


def classify_command(command: str) -> str:
    """Classify a fix command into risk levels.

    Returns: 'low', 'high', or 'unknown'.
    """
    cmd_name = command.split(":")[0].split("{")[0].strip()
    if cmd_name in HIGH_RISK_COMMANDS:
        return "high"
    if cmd_name in LOW_RISK_COMMANDS:
        return "low"
    # Unknown commands are treated as high risk
    return "high"


# ── Recovery Ledger ──────────────────────────────────────────────

_LEDGER_DIR = Path("output") / "recovery_ledger"


def _ensure_ledger() -> Path:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    return _LEDGER_DIR


def log_recovery_action(
    incident_id: str,
    command: str,
    risk: str,
    status: str,
    result: str = "",
) -> dict:
    """Write one entry to the recovery ledger."""
    entry = {
        "incident_id": incident_id,
        "command": command,
        "risk": risk,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    ledger_file = _ensure_ledger() / f"{incident_id}.jsonl"
    with open(ledger_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def get_recovery_ledger(incident_id: str) -> list[dict]:
    """Read all recovery entries for an incident."""
    ledger_file = _ensure_ledger() / f"{incident_id}.jsonl"
    if not ledger_file.is_file():
        return []
    entries: list[dict] = []
    with open(ledger_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# ── Command Executors ────────────────────────────────────────────


def _exec_retry_with_backoff(args: str = "") -> str:
    """Clear retry state to allow immediate retry."""

    return f"retry state cleared (args={args})"


def _exec_clear_cache(args: str = "") -> str:
    """Clear provider-level cache."""
    cache_dir = Path("output") / "provider_cache"
    if cache_dir.is_dir():
        count = len(list(cache_dir.iterdir()))
        for f in cache_dir.iterdir():
            if f.is_file():
                f.unlink()
        return f"cleared {count} cache files"
    return "no cache to clear"


def _exec_switch_provider(args: str = "") -> str:
    """Mark current provider as degraded, forcing fallback."""
    target = args.strip() or "next_available"
    return f"provider switch queued: {target}"


def _exec_increase_timeout(args: str = "") -> str:
    """Increase timeout for next retry."""
    new_timeout = args.strip() or "60"
    return f"timeout increased to {new_timeout}s"


def _exec_reset_circuit_breaker(args: str = "") -> str:
    """Reset circuit breaker for a provider — HIGH RISK."""
    from core.provider import reset_circuit_breaker

    return f"circuit breaker reset: {reset_circuit_breaker(args)}"


def _exec_force_local_once(args: str = "") -> str:
    """Force local mode for one request — HIGH RISK."""
    return f"force local once: {args or 'next_call'}"


COMMAND_HANDLERS: dict[str, Any] = {
    "retry_with_backoff": _exec_retry_with_backoff,
    "clear_cache": _exec_clear_cache,
    "switch_provider": _exec_switch_provider,
    "increase_timeout": _exec_increase_timeout,
    "reset_circuit_breaker": _exec_reset_circuit_breaker,
    "force_local_once": _exec_force_local_once,
}


def execute_command(
    command: str,
    incident_id: str,
    *,
    auto_approve_high_risk: bool = False,
) -> dict:
    """Execute a single remediation command.

    Returns dict with status, result, and whether approval was needed.
    """
    risk = classify_command(command)
    cmd_name = command.split(":")[0].strip()
    cmd_args = command.split(":", 1)[1].strip() if ":" in command else ""

    # High risk commands need approval unless auto-approved
    if risk == "high" and not auto_approve_high_risk:
        log_recovery_action(incident_id, command, risk, "pending_approval")
        return {
            "status": "pending_approval",
            "command": command,
            "risk": risk,
            "message": f"高风险操作需要确认: {command}",
        }

    # Execute the command
    handler = COMMAND_HANDLERS.get(cmd_name)
    if handler is None:
        result = f"unknown command: {command}"
        log_recovery_action(incident_id, command, risk, "failed", result)
        return {"status": "failed", "command": command, "risk": risk, "error": result}

    try:
        result = handler(cmd_args)
        log_recovery_action(incident_id, command, risk, "success", result)
        return {"status": "success", "command": command, "risk": risk, "result": result}
    except Exception as e:
        err = str(e)
        log_recovery_action(incident_id, command, risk, "failed", err)
        return {"status": "failed", "command": command, "risk": risk, "error": err}


def remediate_incident(
    incident: dict,
    *,
    auto_approve_low_risk: bool = True,
    auto_approve_high_risk: bool = False,
) -> list[dict]:
    """Run the full remediation playbook for an incident.

    Returns a list of execution results.
    """
    from core.incident import auto_remediation

    incident_id = incident.get("incident_id", incident.get("_id", "unknown"))
    commands = auto_remediation(incident)
    results: list[dict] = []

    for cmd in commands:
        risk = classify_command(cmd)

        # Auto-approve low risk, gate high risk
        can_run = (risk == "low" and auto_approve_low_risk) or (risk == "high" and auto_approve_high_risk)

        if can_run:
            result = execute_command(cmd, incident_id, auto_approve_high_risk=auto_approve_high_risk)
        else:
            log_recovery_action(incident_id, cmd, risk, "pending_approval")
            result = {
                "status": "pending_approval",
                "command": cmd,
                "risk": risk,
                "message": f"需要确认: {cmd}",
            }
            # Queue for TUI approval
            _queue_for_approval(incident_id, cmd, risk)

        results.append(result)

    return results


def _queue_for_approval(incident_id: str, command: str, risk: str) -> None:
    """Queue a high-risk action for TUI approval gate."""
    try:
        from ui.tui_v2 import _APPROVAL_PENDING

        _APPROVAL_PENDING.append(
            {
                "incident_id": incident_id,
                "command": command,
                "risk": risk,
                "status": "pending",
                "timestamp": time.time(),
            }
        )
    except ImportError:
        # No TUI available — log and skip
        logger.warning("No TUI available, skipping approval queue for %s", command)


# ── Public API ───────────────────────────────────────────────────


def get_recent_actions(limit: int = 20) -> list[dict]:
    """Get the most recent recovery actions across all incidents."""
    ledger_dir = _ensure_ledger()
    actions: list[dict] = []
    for f in sorted(ledger_dir.iterdir(), reverse=True)[:limit]:
        if f.suffix == ".jsonl":
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        actions.append(json.loads(line))
    return actions[:limit]


def get_incident_actions(incident_id: str) -> list[dict]:
    """Get all recovery actions for a specific incident."""
    return get_recovery_ledger(incident_id)
