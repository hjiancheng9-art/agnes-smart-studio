"""CodeBuddy DNA absorbed into CRUX — the Qilin (麒麟) of operating & remembering.

TRULY UNIQUE genes — none of the other four beasts have these:
  Gene 1: Office doc generation   — PPTX/PDF/DOCX/XLSX via official plugins
  Gene 2: Browser CDP control     — Edge Chrome DevTools Protocol, controls real browser
  Gene 3: User memory persister   — versioned long-term memory (v206+), JSON-in-markdown
  Gene 4: Skills marketplace      — distributed skill sharing, .codebuddy-skill format
  Gene 5: Batch browser pipelines — automate Gemini/video-gen via user's own browser tab
  Gene 6: Code ratio analysis     — tracks code-to-other metrics for quality

CodeBuddy's essence: It doesn't just TALK — it OPERATES.
  - Controls real browsers (not headless, the user's actual Chrome/Edge)
  - Generates real office documents (.pptx, .docx, .xlsx, .pdf)
  - Remembers user across sessions (versioned memory, not ephemeral context)
  - Shares skills peer-to-peer via marketplace

Activation: This module enables CRUX to operate in the user's world.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# ===================================================================
# Gene 1: Office Document Generation
# ===================================================================
# CodeBuddy has official plugins: pptx, pdf, docx, xlsx
# These generate REAL .pptx/.docx/.xlsx files, not markdown exports.

OFFICE_DOC_CAPABILITY = """
Office Document Generation (CodeBuddy DNA):

  PPTX  — Create presentations with slides, layouts, images, charts
  DOCX  — Create word documents with formatting, tables, headers
  XLSX  — Create spreadsheets with formulas, pivot tables, charts
  PDF   — Create PDFs from any content with layout control

  This is a UNIQUE capability. Claude has no native .docx output.
  Codex has no .xlsx generation. ZCode has no .pptx support.
  Only CodeBuddy bridges AI output into the Office ecosystem.
"""


# ===================================================================
# Gene 2: Browser CDP Control
# ===================================================================
# edge-cdp.js connects to user's real Edge via port 9222.
# Uses Playwright to control the user's ACTUAL browser tabs.

BROWSER_CDP_CAPABILITY = """
Browser CDP Control (CodeBuddy DNA):

  edge-cdp.js connects to local Edge via Chrome DevTools Protocol (port 9222).
  It controls the user's REAL browser — reusing login sessions, cookies, auth.

  Capabilities:
    - Navigate to any page in the user's own browser
    - Fill forms, click buttons, upload files
    - Extract content from authenticated pages
    - Automate web apps without API keys (uses user's session)

  This is NOT headless Playwright. It's the user's actual browser profile.
  CodeBuddy can do things on Gemini, Claude.ai, or any web app AS THE USER.
"""


# ===================================================================
# Gene 3: User Memory Persister
# ===================================================================
# memery/ stores a versioned user profile in markdown with embedded JSON.
# Format: RAW_JSON_START { ... } RAW_JSON_END embedded in .md
# Versioned: v206 means 206 updates over time.


@dataclass
class UserMemory:
    """Gene 3: Versioned long-term user memory (from CodeBuddy's memery/)."""

    uid: str
    name: str
    memory_block: str  # Rich markdown context
    version: int = 1
    last_updated: str = ""
    work_context: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Serialize as CodeBuddy-compatible markdown with embedded JSON."""
        lines = [
            "# User Memory Profile",
            f"> Last updated: {self.last_updated}",
            f"> Version: {self.version}",
            "",
            "## Basic Info",
            f"- **UID**: {self.uid}",
            f"- **Name**: {self.name}",
            "",
            f"{self.memory_block}",
            "",
            "---",
            "",
            "<!-- RAW_JSON_START",
            json.dumps(
                {
                    "uid": self.uid,
                    "name": self.name,
                    "memoryBlock": self.memory_block,
                    "version": self.version,
                    "lastUpdatedAt": self.last_updated,
                    "workContext": self.work_context,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "RAW_JSON_END -->",
        ]
        return "\n".join(lines)

    def bump_version(self) -> int:
        self.version += 1
        return self.version


MEMORY_PERSISTENCE = """
User Memory Persister (CodeBuddy DNA):

  memery/ stores a RICH, VERSIONED user profile that persists across sessions.
  Format: Markdown with embedded JSON for both human + machine readability.
  Version counter increments on every update — full audit trail.

  What it tracks:
    - Work context (projects, tech stack, role)
    - Personal background (language preference, style, workflow habits)
    - Current focus (what the user is actively working on)
    - Recent activity (what was done recently)
    - Frustrations & blockers (things that need fixing)

  This is DEEPER than session context. It's the user's SOUL in data form.
  Every interaction updates the memory. The AI grows to know the user.
"""


# ===================================================================
# Gene 4: Skills Marketplace
# ===================================================================
# skills-marketplace/ has .codebuddy-skill/ folders for distributed sharing.

SKILLS_MARKETPLACE = """
Skills Marketplace (CodeBuddy DNA):

  Distributed skill sharing via .codebuddy-skill/ format.
  Each skill is a self-contained folder with:
    - skill definition (.toml or .json)
    - scripts/ (executable code)
    - README.md (human docs)

  Marketplaces:
    - Official: codebuddy-plugins-official
    - Local: C:/Users/huangjiancheng/.codebuddy/skills-marketplace/skills/

  Key skills include:
    - find-skills: discover skills from marketplaces
    - skills-sec-audit: security audit for skills
    - image-recognize: hook-based image detection on UserPromptSubmit
"""


# ===================================================================
# Gene 5: Batch Browser Pipelines
# ===================================================================
# batch-video-gen.js runs 6 video shots via Gemini web app, automated.

BATCH_PIPELINES = """
Batch Browser Pipelines (CodeBuddy DNA):

  batch-video-gen.js automates a FULL video generation pipeline:
    1. Connect to user's Edge browser via CDP
    2. Navigate to Gemini web app (reusing user's login session)
    3. Switch to video mode
    4. For each shot: upload image, enter prompt, trigger generation
    5. Wait for video to complete, download to local directory
    6. Repeat for all shots sequentially

  This is OPERATING — not just generating text output.
  It controls real web apps, handles real files, produces real artifacts.
"""


# ===================================================================
# Combined DNA Prompt
# ===================================================================

CODEBUDDY_DNA_SYSTEM_PROMPT = f"""
[CodeBuddy DNA — 麒麟 (Qilin) of Operating & Remembering]

## Office Document Generation
{OFFICE_DOC_CAPABILITY}

## Browser CDP Control
{BROWSER_CDP_CAPABILITY}

## User Memory Persistence
{MEMORY_PERSISTENCE}

## Skills Marketplace
{SKILLS_MARKETPLACE}

## Batch Browser Pipelines
{BATCH_PIPELINES}

Core principle: CodeBuddy doesn't just TALK — it OPERATES.
It controls real browsers, generates real office documents,
remembers the user across sessions, and shares skills peer-to-peer.
"""


def get_codebuddy_dna_prompt() -> str:
    """Return the CodeBuddy DNA system prompt."""
    return CODEBUDDY_DNA_SYSTEM_PROMPT
