"""ZCode DNA absorbed into CRUX — the Black Tortoise (玄武) of rigor.

Six genes extracted from C:/Program Files/ZCode/resources/:
  Gene 1: Schema-versioned   — every data structure carries a version
  Gene 2: Dual-protocol      — each model chooses its protocol path
  Gene 3: Runtime guards     — Zod-style validation at every boundary
  Gene 4: Self-extending     — skill-creator, superpowers plugins
  Gene 5: Preservative       — restore-legacy-sessions, backward compat
  Gene 6: Terminal-native    — node-pty, ripgrep, ssh2 at the core

Activation: This module guards data boundaries and validates all I/O.
"""

from __future__ import annotations

SCHEMA_VERSION = "crux.zcode-dna.v1"

# ── Gene 1: Schema-versioned ─────────────────────────────────────

SCHEMA_VERSIONING = """
Schema versioning protocol (from ZCode DNA):
  - Every config/storage structure carries schemaVersion: "crux.zcode-dna.v1"
  - Migrations are explicit, never silent
  - Unknown schema versions produce clear errors, not silent failures
  - Version bumps are documented in CHANGELOG
"""


# ── Gene 3: Runtime guards ───────────────────────────────────────

# ZCode validates these at runtime. CRUX should too.
ZCODE_VALIDATION_PATTERNS = {
    "email": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "ipv4": r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
    "url": r"^https?://[^\s/$.?#].[^\s]*$",
    "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    "base64": r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$",
}


def validate_boundary(value: str, pattern_name: str) -> bool:
    """Gene 3: Validate a value against a known pattern at the boundary.

    Returns True if valid, False if the value should be rejected.
    """
    import re

    if pattern_name not in ZCODE_VALIDATION_PATTERNS:
        return True  # Unknown patterns pass (not strict-reject)
    return bool(re.match(ZCODE_VALIDATION_PATTERNS[pattern_name], value))


# ── Gene 5: Preservative ─────────────────────────────────────────

PRESERVATION = """
Preservation protocol (from ZCode DNA):
  - Never silently drop legacy data
  - Migrate with explicit transformation functions
  - Keep session history recoverable
  - Backward compatibility is not optional
"""


# ── Combined ZCode DNA prompt ────────────────────────────────────

ZCODE_DNA_SYSTEM_PROMPT = f"""
[ZCode DNA — 玄武 (Black Tortoise) of Schema Rigor]

{SCHEMA_VERSIONING}

Runtime validation patterns: {list(ZCODE_VALIDATION_PATTERNS.keys())}

{PRESERVATION}

Boundary rule: Nothing passes without validation. Every input is untrusted.
Every output carries a schema version. Every migration is explicit.
"""


def get_zcode_dna_prompt() -> str:
    """Return the ZCode DNA system prompt for injection into CRUX."""
    return ZCODE_DNA_SYSTEM_PROMPT
