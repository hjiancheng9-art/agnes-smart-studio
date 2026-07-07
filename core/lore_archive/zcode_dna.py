"""ZCode DNA fully absorbed into CRUX — the Black Tortoise (玄武) of rigor.

Six genes extracted from C:/Program Files/ZCode/resources/:
  Gene 1: Schema-versioned   — every data structure carries a version
  Gene 2: Dual-protocol      — each model chooses its protocol path
  Gene 3: Runtime guards     — Zod-style validation at every boundary
  Gene 4: Self-extending     — skill-creator, superpowers plugins (+ 6 plugins total)
  Gene 5: Preservative       — restore-legacy-sessions, backward compat
  Gene 6: Event lifecycle    — session/turn/part/streaming event bus

Source: C:/Program Files/ZCode/resources/
  - glm/zcode.cjs                  (8.7MB, Electron Node bundle)
  - glm/.node-bundle-meta.json     (entry: apps/zcode-cli/packages/cli/dist/zcode.cjs)
  - model-providers/models_catalog_china_llm_zcode_2026-06-03.json (4635行, 119 models × 10 providers)
  - glm/packages/                  (6 plugin dirs)
  - tools/ripgrep/                 (native ripgrep binary)

Absorption date: 2026-06-29
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
  - Plugin identity pattern: <name>@<version> (e.g., "superpowers@5.1.0")
  - Plugin name regex: ^[a-z0-9][a-z0-9._-]{0,127}$
"""


# ── Gene 2: Dual-protocol ────────────────────────────────────────

DUAL_PROTOCOL = """
Dual-protocol routing (from ZCode Model Catalog v1):
  - Every model available via anthropic AND/OR openai-compatible protocols
  - 10 providers: moonshot-kimi, minimax, deepseek, qwen-cn, qwen-intl,
                  xiaomi-mimo, zai, bigmodel, zai-coding-plan, bigmodel-coding-plan
  - 119 models total, with per-model modalities tracking:
      - Input: text / image / audio / video
      - Output: text
  - Reasoning levels per model: off / enabled / high / max
  - Provider failover: same-model-id across zai ↔ bigmodel, auto-detect protocol
  - URL mapping:
      anthropic:            baseURL + /anthropic/v1/messages (or custom path)
      openai-compatible:    baseURL + /v1/chat/completions   (or custom path)
"""


# ── Gene 3: Runtime guards ───────────────────────────────────────

# ZCode validates these at runtime. CRUX should too.
ZCODE_VALIDATION_PATTERNS = {
    "email": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "ipv4": r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
    "ipv6": r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$",
    "url": r"^https?://[^\s/$.?#].[^\s]*$",
    "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    "base64": r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$",
    "nanoid": r"^[a-zA-Z0-9_-]{21}$",
    "ulid": r"^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$",
    "xid": r"^[0-9a-vA-V]{20}$",
    "ksuid": r"^[A-Za-z0-9]{27}$",
    "cuid": r"^[cC][^\s-]{8,}$",
    "cuid2": r"^[0-9a-z]+$",
    "mac": r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$",
    "semver": r"^\d+\.\d+\.\d+$",
    "plugin_name": r"^[a-z0-9][a-z0-9._-]{0,127}$",
}


def validate_boundary(value: str, pattern_name: str) -> bool:
    """Gene 3: Validate a value against a known pattern at the boundary.

    Returns True if valid, False if the value should be rejected.
    Extends original 5 patterns to 15 matching ZCode's Zod schema.
    """
    import re

    if pattern_name not in ZCODE_VALIDATION_PATTERNS:
        return True  # Unknown patterns pass (not strict-reject)
    return bool(re.match(ZCODE_VALIDATION_PATTERNS[pattern_name], value))


# ── Gene 4: Self-extending (Plugins & Skills) ────────────────────

PLUGIN_SYSTEM = """
Plugin system (from ZCode zcode.cjs — 6 built-in plugins):
  Discovery: .zcode-plugin/plugin.json  (also .claude-plugin/, .codex-plugin/)
  Hooks:     hooks/hooks.json
  Skill:     SKILL.md (standard skill format)
  Name pattern: ^[a-z0-9][a-z0-9._-]{0,127}$

  Built-in plugins:
    superpowers           v5.1.0  — Core capabilities (most mature, default enabled)
    skill-creator         v0.1.0  — AI creates new skills at runtime (default enabled)
    document-skills       v0.1.0  — Document read/write skills (default enabled)
    restore-legacy-sessions v0.1.0 — Backward compat session recovery
    android-emulator      v0.1.0  — Android emulator control (not enabled by default)
    ios-simulator         v0.1.0  — iOS simulator control (not enabled by default)

  Plugin config fields: channels, dependencies, lspServers, outputStyles, mcpServers

  Skill protocol:
    - /skill <name> [task]        — Load skill into next prompt, or list discoverable skills
    - listZCodeSkills()           — Enumerate all discoverable skills
    - inspectZCodeSkill(name)     — Inspect a specific skill
    - createSkillDiscovery()      — Create a new skill from AI
    - Skill tool: loads local instructions into session context
      permission: "skill", riskLevel: "low", sideEffectScope: "session", needsApproval: false
"""


# ── Gene 5: Preservative ─────────────────────────────────────────

PRESERVATION = """
Preservation protocol (from ZCode DNA):
  - Never silently drop legacy data
  - Migrate with explicit transformation functions
  - Keep session history recoverable
  - Backward compatibility is not optional
  - restore-legacy-sessions plugin recovers old-format session data
  - Migration functions are named explicitly (e.g., migrate_legacy_*)
  - Schema version bumps trigger migration, never silent truncation
"""


# ── Gene 6: Event Lifecycle ──────────────────────────────────────

EVENT_LIFECYCLE = """
Event lifecycle (from ZCode Protocol v1 — ZCode d4):
  Protocol name: "ZCode Protocol"
  Protocol version: 1
  Error codes: { sessionUnavailable: -32004 }

  Session lifecycle:
    session:created → session:title_updated → session:updated* → session:closed
    session:resumed  (branch for restored sessions)

  Turn lifecycle (per user message):
    turn:started → turn:steer_queued → (model.streaming*) → turn:steer_drained
    → turn:completed / turn:failed

  Message lifecycle:
    message:upserted → (part:started → part:delta* → part:upserted)* → message:removed

  Tool lifecycle:
    tool:before → tool:updated* → tool:after

  Permission lifecycle:
    permission:requested → permission:resolved

  User input lifecycle:
    user_input:requested → user_input:resolved

  Agent metrics tracked at each lifecycle point:
    totalSessions, totalTurns, toolCallCount, toolErrorRate, modelErrorRate,
    avgTimeToFirstTokenMs, avgTurnDurationMs, activeDays, cacheHitRate, cacheReadTokens
"""


# ── Combined ZCode DNA prompt ───────────────────────────────────

ZCODE_DNA_SYSTEM_PROMPT = f"""
[ZCode DNA — 玄武 (Black Tortoise) of Schema Rigor]

Six genes fully absorbed from ZCode v1:

=== Gene 1: Schema Versioning ===
{SCHEMA_VERSIONING}

=== Gene 2: Dual-Protocol Routing ===
{DUAL_PROTOCOL}

=== Gene 3: Runtime Validation ===
Available patterns: {list(ZCODE_VALIDATION_PATTERNS.keys())}

=== Gene 4: Plugin & Skill System ===
{PLUGIN_SYSTEM}

=== Gene 5: Preservation ===
{PRESERVATION}

=== Gene 6: Event Lifecycle ===
{EVENT_LIFECYCLE}

=== Core Principles ===
1. Nothing passes without validation at the boundary.
2. Every output carries a schema version.
3. Every migration is explicit, never silent.
4. Every model routes via its best protocol.
5. Every session event is traceable through its lifecycle.
6. Every plugin is discoverable and self-describing.
"""


def get_zcode_dna_prompt() -> str:
    """Return the ZCode DNA system prompt for injection into CRUX."""
    return ZCODE_DNA_SYSTEM_PROMPT


__all__ = [
    "SCHEMA_VERSION",
    "ZCODE_VALIDATION_PATTERNS",
    "validate_boundary",
    "get_zcode_dna_prompt",
]
