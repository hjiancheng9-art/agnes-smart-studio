#!/usr/bin/env python3
"""
Convert anthropics/skills SKILL.md files to CRUX .skill.json format.

Usage: python scripts/convert_anthropics_skills.py [--all] [--dry-run]

Downloads SKILL.md from raw.githubusercontent.com/anthropics/skills/main/skills/{name}/SKILL.md
Parses YAML frontmatter + markdown body, outputs to skills/{name}.skill.json
"""

import json
import os
import sys
import urllib.error
import urllib.request

# ── Skill list ──────────────────────────────────────────────
ANTHROPICS_SKILLS = [
    "algorithmic-art",
    "brand-guidelines",
    "claude-api",
    "doc-coauthoring",
    "docx",
    "frontend-design",
    "internal-comms",
    "pdf",
    "pptx",
    "skill-creator",
    "slack-gif-creator",
    "theme-factory",
    "web-artifacts-builder",
    "webapp-testing",
    "xlsx",
]

BASE_URL = "https://raw.githubusercontent.com/anthropics/skills/main/skills"
OUTPUT_DIR = "skills"

# Category mapping for descriptions
CATEGORY_EMOJI = {
    "algorithmic-art": "🎨",
    "brand-guidelines": "🏷️",
    "claude-api": "🔌",
    "doc-coauthoring": "📝",
    "docx": "📄",
    "frontend-design": "🎨",
    "internal-comms": "💬",
    "pdf": "📕",
    "pptx": "📊",
    "skill-creator": "🛠️",
    "slack-gif-creator": "🎬",
    "theme-factory": "🎭",
    "web-artifacts-builder": "🌐",
    "webapp-testing": "🧪",
    "xlsx": "📗",
}


def parse_skill_md(text: str) -> tuple[str, str, dict]:
    """Parse YAML frontmatter + markdown body from SKILL.md."""
    text = text.strip()
    if not text.startswith("---"):
        return {"name": "unknown", "description": ""}, text

    # Find second ---
    end_idx = text.find("---", 3)
    if end_idx == -1:
        return {"name": "unknown", "description": ""}, text

    frontmatter_text = text[3:end_idx].strip()
    body = text[end_idx + 3 :].strip()

    # Simple YAML parse (no pyyaml dependency needed for this subset)
    meta = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Remove quotes
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            meta[key] = value

    return meta, body


def download_skill(name: str) -> str | None:
    """Download SKILL.md for a given skill name."""
    url = f"{BASE_URL}/{name}/SKILL.md"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CRUX-Studio/6.0",
            "Accept": "text/plain",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  [HTTP {e.code}] {url}")
        return None
    except Exception as e:
        print(f"  [Error] {url}: {e}")
        return None


def build_skill_json(name: str, meta: dict, body: str) -> dict:
    """Build CRUX .skill.json from parsed metadata."""
    description = meta.get("description", "")
    emoji = CATEGORY_EMOJI.get(name, "🔧")

    # Build a richer description if the original is short
    if description and not description.startswith(emoji):
        description = f"{emoji} {description}"

    return {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "author": "anthropics",
        "target": "code",
        "models": ["deepseek-v4-flash"],
        "always_load": False,
        "prompt": [
            {
                "type": "text",
                "content": body.strip(),
            }
        ],
    }


def main():
    dry_run = "--dry-run" in sys.argv
    process_all = "--all" in sys.argv or dry_run

    # If --all, process all; otherwise only missing ones
    skills_to_process = list(ANTHROPICS_SKILLS)

    if not process_all:
        existing = set()
        if os.path.isdir(OUTPUT_DIR):
            for f in os.listdir(OUTPUT_DIR):
                if f.endswith(".skill.json"):
                    existing.add(f[: -len(".skill.json")])
        skills_to_process = [s for s in skills_to_process if s not in existing]
        print(f"Already have {len(existing)} skills, need to download {len(skills_to_process)}")

    print(f"\n{'=' * 60}")
    print(f"Converting {len(skills_to_process)} anthropics skills to CRUX format")
    print(f"{'=' * 60}\n")

    success = 0
    failed = 0
    skipped = 0

    for name in skills_to_process:
        print(f"  [{success + failed + skipped + 1}/{len(skills_to_process)}] {name}...", end=" ")

        text = download_skill(name)
        if text is None:
            print("DOWNLOAD FAILED")
            failed += 1
            continue

        meta, body = parse_skill_md(text)
        if not body.strip():
            print("EMPTY BODY")
            failed += 1
            continue

        skill = build_skill_json(name, meta, body)
        output_path = os.path.join(OUTPUT_DIR, f"{name}.skill.json")

        if dry_run:
            print(f"OK (would write {len(body)} chars → {output_path})")
            success += 1
            continue

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(skill, f, indent=2, ensure_ascii=False)
            print(f"✅ {len(body)} chars → {output_path}")
            success += 1
        except Exception as e:
            print(f"WRITE ERROR: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Done: {success} success, {failed} failed, {skipped} skipped")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
