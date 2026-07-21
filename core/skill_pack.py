"""Skill pack format — serializable, distributable skill bundles.

.crux-skill files are ZIP archives containing:
    skill.json      — the skill definition (name, description, prompt, category)
    metadata.json   — version, author, requires, license
    assets/         — optional icons, templates, scripts

Usage:
    python core/skill_pack.py pack code-review          → code-review.crux-skill
    python core/skill_pack.py install code-review.crux-skill  → installs to skills/
    python core/skill_pack.py install https://.../skill.crux-skill  → download + install
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
PACK_EXT = ".crux-skill"


def pack(skill_name: str, output_dir: str | None = None) -> Path:
    """Pack a skill into a .crux-skill zip file.

    Args:
        skill_name: name of skill to pack (looks in skills/ for <name>.json or <name>.skill.json)
        output_dir: where to write the .crux-skill file (default: current dir)
    Returns: path to the created .crux-skill file
    """
    # Find the skill file
    candidates = [
        SKILLS_DIR / f"{skill_name}.skill.json",
        SKILLS_DIR / f"{skill_name}.json",
        ROOT / "skills_md" / f"{skill_name}.skill.md",
    ]
    skill_path = None
    for p in candidates:
        if p.is_file():
            skill_path = p
            break
    if not skill_path:
        raise FileNotFoundError(f"skill '{skill_name}' not found in skills/ or skills_md/")

    data = json.loads(skill_path.read_text(encoding="utf-8")) if skill_path.suffix == ".json" else None
    if data is None and skill_path.suffix == ".md":
        text = skill_path.read_text(encoding="utf-8", errors="replace")
        data = {"name": skill_name, "description": skill_name, "prompt": text, "category": "general"}
    if data is None:
        data = {"name": skill_name, "description": skill_name, "category": "general"}

    metadata = {
        "version": data.get("version", "1.0.0"),
        "author": data.get("author", "CRUX Community"),
        "requires": data.get("requires", []),
        "license": data.get("license", "MIT"),
        "packed_at": __import__("datetime").datetime.now().isoformat(),
    }

    out_dir = Path(output_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_path = out_dir / f"{skill_name}{PACK_EXT}"

    with zipfile.ZipFile(pack_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("skill.json", json.dumps(data, indent=2, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
        # Include assets if present
        assets_dir = SKILLS_DIR / skill_name
        if assets_dir.is_dir():
            for f in assets_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f"assets/{f.relative_to(assets_dir)}")

    logger.info("Packed %s → %s (%d bytes)", skill_name, pack_path.name, pack_path.stat().st_size)
    return pack_path


def install(source: str) -> dict:
    """Install a skill from a .crux-skill file or URL.

    Args:
        source: path to .crux-skill file, or http(s) URL
    Returns: dict with name, status, path
    """
    # Download if URL
    if source.startswith(("http://", "https://")):
        try:
            import urllib.request

            tmp = tempfile.NamedTemporaryFile(suffix=PACK_EXT, delete=False)
            urllib.request.urlretrieve(source, tmp.name)  # nosec B310
            source = tmp.name
        except Exception as e:
            return {"name": source, "status": "error", "error": f"download failed: {e}"}

    pack_path = Path(source)
    if not pack_path.is_file():
        return {"name": source, "status": "error", "error": f"file not found: {source}"}

    try:
        with zipfile.ZipFile(pack_path) as zf:
            if "skill.json" not in zf.namelist():
                return {"name": source, "status": "error", "error": "invalid pack: missing skill.json"}
            data = json.loads(zf.read("skill.json"))
            name = data.get("name", pack_path.stem)
            # Write to skills/
            dest = SKILLS_DIR / f"{name}.skill.json"
            dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            # Extract assets
            for entry in zf.namelist():
                if entry.startswith("assets/") and not entry.endswith("/"):
                    asset_path = SKILLS_DIR / name / entry[len("assets/") :]
                    asset_path.parent.mkdir(parents=True, exist_ok=True)
                    asset_path.write_bytes(zf.read(entry))
            # Metadata
            if "metadata.json" in zf.namelist():
                meta = json.loads(zf.read("metadata.json"))
                (SKILLS_DIR / f"{name}.meta.json").write_text(
                    json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        return {"name": name, "status": "installed", "path": str(dest)}
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as e:
        return {"name": source, "status": "error", "error": f"invalid pack: {e}"}


def list_packs(directory: str | None = None) -> list[dict]:
    """List all .crux-skill packs in a directory."""
    d = Path(directory or ".")
    if not d.is_dir():
        return []
    packs = []
    for f in sorted(d.glob(f"*{PACK_EXT}")):
        try:
            with zipfile.ZipFile(f) as zf:
                if "skill.json" in zf.namelist():
                    data = json.loads(zf.read("skill.json"))
                    meta = json.loads(zf.read("metadata.json")) if "metadata.json" in zf.namelist() else {}
                    packs.append(
                        {
                            "file": f.name,
                            "name": data.get("name", f.stem),
                            "version": meta.get("version", "1.0.0"),
                            "author": meta.get("author", ""),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                        }
                    )
        except (zipfile.BadZipFile, json.JSONDecodeError):
            pass
    return packs


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "pack" and len(sys.argv) >= 3:
        out = pack(sys.argv[2])
        print(f"Packed: {out}")
    elif cmd == "install" and len(sys.argv) >= 3:
        result = install(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "list":
        packs = list_packs()
        for p in packs:
            print(f"  {p['file']} — {p['name']} v{p['version']} ({p['size_kb']}KB)")
    else:
        print("Usage: python core/skill_pack.py pack <skill_name>")
        print("       python core/skill_pack.py install <file|url>")
        print("       python core/skill_pack.py list")
