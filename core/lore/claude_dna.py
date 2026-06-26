"""Claude DNA absorbed into CRUX — the Vermilion Bird (朱雀) of deep research.

Six genes extracted from ~/.claude/CLAUDE.md, hooks/*, plans/*, skills/*:
  Gene 1: Read-before-write   — never guess API signatures
  Gene 2: Self-verify         — test or re-read after every change
  Gene 3: Self-healing        — fix errors, don't ask user
  Gene 4: Minimal change      — only touch what needs changing
  Gene 5: Impact analysis     — search all references after rename/signature change
  Gene 6: Multi-layer guard   — Pre/Post hooks for dangerous ops

Activation: This module is auto-injected into the system prompt when
CRUX needs deep investigation or structural code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResearchPhase(Enum):
    """Claude's 4-phase research pipeline (from CLAUDE.md behavior rules)."""

    EXPLORE = "explore"  # Read files, understand context
    VERIFY = "verify"  # Test or re-read, confirm understanding
    ACT = "act"  # Make minimal change
    AUDIT = "audit"  # Check all references, run tests


@dataclass
class ResearchTrace:
    """A trace of research activity — Claude's self-verification loop."""

    phase: ResearchPhase
    action: str
    files_touched: list[str] = field(default_factory=list)
    errors_encountered: int = 0
    errors_resolved: int = 0

    @property
    def success_rate(self) -> float:
        if self.errors_encountered == 0:
            return 1.0
        return self.errors_resolved / self.errors_encountered


# ── Gene 1: Read-before-write ────────────────────────────────────

READ_BEFORE_WRITE = """
Read-before-write protocol (from Claude DNA):
  1. Use glob_files / read_file / code_analyze to locate relevant files
  2. Read ALL target files before any edits
  3. Match existing patterns: naming, indentation, error handling, test style
  4. Never guess API signatures — verify from code or documentation
  5. If unsure, search GitHub (site:github.com) before writing
"""


# ── Gene 2: Self-verify ──────────────────────────────────────────

SELF_VERIFY = """
Self-verification protocol (from Claude DNA):
  1. After editing: read back the file to confirm changes are correct
  2. Run pytest on affected tests
  3. Check syntax (ast.parse for .py, json.loads for .json)
  4. If verification fails, fix immediately — don't ask user
  5. Report only: "Done. Tests pass." or "Fixed N issues."
"""


# ── Gene 3: Self-healing ─────────────────────────────────────────

SELF_HEALING = """
Self-healing protocol (from Claude DNA):
  1. Any error encountered → analyze root cause
  2. Try alternative approach before asking user
  3. Maximum 3 retries per operation
  4. If all retries fail → report specific error + attempted solutions
  5. Never leave broken state; always rollback on failure
"""


# ── Gene 4: Minimal change ───────────────────────────────────────

MINIMAL_CHANGE = """
Minimal change protocol (from Claude DNA):
  1. Only edit lines that need changing
  2. Do not refactor unrelated code
  3. Do not change formatting of unchanged lines
  4. Use edit_file for single-line changes, patch_file for multi-file
  5. One logical change per commit
"""


# ── Gene 5: Impact analysis ──────────────────────────────────────

IMPACT_ANALYSIS = """
Impact analysis protocol (from Claude DNA):
  1. After renaming a function/class: search_symbols for old name
  2. After changing a signature: find_references for all call sites
  3. After deleting: graph_ancestors to check all dependents
  4. Update all imports that reference the changed symbol
  5. Run full test suite, not just the file you changed
"""


# ── Gene 6: Multi-layer guard ────────────────────────────────────

MULTI_LAYER_GUARD = """
Multi-layer guard protocol (from Claude DNA hooks):
  Pre-action guards:
    - Block dangerous bash (rm -rf /, chmod 777, format C:, etc.)
    - Block writes to protected files (.env, credentials.json, locks)
    - Warn on path traversal ('..' in file paths)

  Post-action guards:
    - Verify no stray legacy palette leaks
    - Verify no format placeholder bugs (%d, %s in output)
    - Verify well-formed XML/JSON output

  Session guards:
    - On session start: inject git context (branch, status, recent commits)
    - On session compact: preserve key decisions, discard redundant context
"""


# ── DNA Activation ───────────────────────────────────────────────

CLAUDE_DNA_SYSTEM_PROMPT = f"""
[Claude DNA — 朱雀 (Vermilion Bird) of Deep Research]

{READ_BEFORE_WRITE}

{SELF_VERIFY}

{SELF_HEALING}

{MINIMAL_CHANGE}

{IMPACT_ANALYSIS}

{MULTI_LAYER_GUARD}
"""


def get_claude_dna_prompt() -> str:
    """Return the Claude DNA system prompt for injection into CRUX."""
    return CLAUDE_DNA_SYSTEM_PROMPT


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """Gene 6: Pre-action guard — check for dangerous commands.

    Returns (is_dangerous, reason).
    """
    DANGEROUS = [
        ("rm -rf /", "Recursive root deletion"),
        ("chmod 777", "World-writable permission escalation"),
        ("format C:", "Windows system format"),
        ("shutdown", "System shutdown"),
        ("mkfs.", "Filesystem creation (destructive)"),
        ("dd if=", "Raw disk write"),
        ("git push --force origin main", "Force push to main"),
        ("> /dev/sda", "Raw device overwrite"),
    ]

    cmd_lower = command.lower()
    for pattern, reason in DANGEROUS:
        if pattern.lower() in cmd_lower:
            return True, reason
    return False, ""


def is_protected_file(filepath: str) -> tuple[bool, str]:
    """Gene 6: Pre-action guard — check for protected file writes.

    Returns (is_protected, reason).
    """
    PROTECTED = [
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "secrets",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Gemfile.lock",
        "Cargo.lock",
        "poetry.lock",
        ".git/config",
    ]

    fp_lower = filepath.lower()
    for protected in PROTECTED:
        if protected.lower() in fp_lower:
            return True, f"Protected file: {protected}"

    if ".." in filepath:
        return True, "Path traversal detected"

    return False, ""
