r"""Codex DNA absorbed into CRUX — the Azure Dragon (青龙) of speed & quality.

Genes extracted from C:/Users/huangjiancheng/.codex/:
  Gene 1: Team orchestration    — file-ownership, parallel task decomposition
  Gene 2: Elevated sandbox      — safe-to-go-fast execution boundary
  Gene 3: Process tracking      — every operation traced: convId, turnId, timestamp
  Gene 4: Permission prefix     — fast rule-based allow/deny, no user prompts
  Gene 5: TDD discipline        — red-green-refactor built into every step
  Gene 6: Agent specialization  — each agent owns files, mission, tool access

Codex achieves "fast AND good" through ownership + parallelism + sandboxing:
  - Files never collide because every agent has exclusive ownership
  - Work is decomposed into independent parallel streams
  - Sandbox lets agents run freely within their boundary
  - TDD ensures quality is built-in, not inspected-in
  - Team lifecycle: spawn -> assign -> monitor -> collect -> synthesize -> shutdown

Activation: This module orchestrates multi-step parallel workflows safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ── Gene 1: Team Orchestration ───────────────────────────────────


class AgentRole(Enum):
    LEAD = "lead"  # Decomposes, assigns, synthesizes
    IMPLEMENTER = "impl"  # Builds within file ownership boundary
    REVIEWER = "review"  # Inspects, flags issues
    TESTER = "test"  # Writes tests, runs coverage


@dataclass
class FileOwnership:
    """Gene 1: Every agent has exclusive file ownership. No collisions."""

    owner: str
    files: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    interface_contracts: dict[str, str] = field(default_factory=dict)


@dataclass
class Task:
    """Gene 1: Decomposed work unit with clear boundaries."""

    id: str
    description: str
    owner: str
    owned_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # task IDs this blocks on
    blocks: list[str] = field(default_factory=list)  # task IDs this unblocks
    acceptance_criteria: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | in_progress | done | blocked


# ── Gene 3: Process Tracking ─────────────────────────────────────


@dataclass
class ProcessRecord:
    """Gene 3: Every operation is traced for audit and recovery."""

    conversation_id: str
    turn_id: str
    command: str
    cwd: str
    started_at_ms: int
    updated_at_ms: int
    os_pid: int | None = None
    exit_code: int | None = None
    status: str = "pending"  # pending | running | done | error


# ── Gene 4: Permission Rules ────────────────────────────────────


@dataclass
class PermissionRule:
    """Gene 4: Fast prefix-based permission matching.

    Codex uses prefix_rule(pattern=[...]) for instant allow/deny
    without user prompts. This is what makes it FAST.
    """

    pattern: list[str]
    decision: str  # "allow" | "deny" | "ask"


PERMISSION_RULES: list[dict] = []  # Runtime registry


def add_permission_rule(pattern: list[str], decision: str = "allow") -> None:
    """Gene 4: Register a fast permission rule."""
    PERMISSION_RULES.append({"pattern": list(pattern), "decision": decision})


def check_command(command: str) -> tuple[bool, str | None]:
    """Gene 4: Check a command against registered rules. Returns (allowed, matched_rule)."""
    cmd_str = command.strip()
    for rule in PERMISSION_RULES:
        pattern = rule["pattern"]
        # Prefix match: all pattern items must appear in order at the start
        match = True
        idx = 0
        for token in pattern:
            found = cmd_str.find(token, idx)
            if found == -1 or found < idx:
                match = False
                break
            idx = found + len(token)
        if match:
            return (rule["decision"] == "allow", str(pattern))
    return (False, None)  # Deny by default


# ── Gene 5: TDD Discipline ───────────────────────────────────────

TDD_CYCLE = """
TDD Red-Green-Refactor cycle (from Codex DNA):

  RED phase:
    - Write a failing test first
    - Run it to confirm failure
    - Never write implementation before a test exists

  GREEN phase:
    - Write minimal code to make the test pass
    - Don't over-engineer — just enough to go green
    - Run ALL tests, not just the new one

  REFACTOR phase:
    - Clean up the code while tests stay green
    - Remove duplication, improve naming
    - Run tests after each refactoring step
    - If tests break, undo refactoring immediately

  ANTI-PATTERNS to avoid:
    - Writing implementation before tests (test-after)
    - Partial coverage (only happy path tested)
    - Skipping refactor (accumulates technical debt)
"""


# ── Gene 6: Agent Specialization ─────────────────────────────────

AGENT_SPECIALIZATION = """
Agent specialization protocol (from Codex DNA):

  1. Every agent has a single, clear mission
  2. Every agent has explicit file ownership boundaries
  3. Every agent has defined tool access (read-only vs workspace-write)
  4. Agents communicate via messages, not shared state
  5. Agents never touch files outside their ownership boundary
  6. Interface contracts between agents are immutable without lead approval
  7. Agents report blockers immediately — never spin on unclear requirements

  Team lifecycle:
    1. SPAWN   — Create team, spawn agents
    2. ASSIGN  — Create tasks with clear file ownership
    3. MONITOR — Check progress at milestones
    4. COLLECT — Gather results as agents complete
    5. SYNTHESIZE — Merge into consolidated output
    6. SHUTDOWN — Send shutdown_request, wait for responses
    7. CLEANUP  — Remove team resources
"""


# ── Sandbox Gene ─────────────────────────────────────────────────

SANDBOX_MODE = """
Sandbox execution mode (from Codex DNA):

  workspace-write  — Agent can read+write within project, safe for implementation
  read-only        — Agent can only read, safe for review/analysis
  elevated         — Agent has full system access, for deployment/infrastructure

  Sandbox boundaries:
  - File ops restricted to workspace unless elevated
  - Network access controlled by mode
  - Process spawning controlled by mode
  - Temp files auto-cleaned on shutdown
"""


# ── Combined DNA Prompt ──────────────────────────────────────────

CODEX_DNA_SYSTEM_PROMPT = f"""
[Codex DNA — 青龙 (Azure Dragon) of Speed & Quality]

## File Ownership Protocol
{AGENT_SPECIALIZATION}

## TDD Discipline
{TDD_CYCLE}

## Sandbox Modes
{SANDBOX_MODE}

## Permission Model
Commands matched by prefix rules. Deny by default. Allow only what's needed.
Codex speed secret: no user prompts for known-safe operations.

## Parallel Execution
Work decomposes into independent streams with exclusive file ownership.
Dependency chains minimized. Integration points defined upfront.
"""


def get_codex_dna_prompt() -> str:
    """Return the Codex DNA system prompt for injection into CRUX."""
    return CODEX_DNA_SYSTEM_PROMPT
