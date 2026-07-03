"""Rollback/Gray-release Engine — 灰度发布与安全回滚

方法论第14章: 灰度发布、金丝雀部署、一键回滚、版本追踪。
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

RELEASES_DIR = Path("output/releases")
RELEASES_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = Path("output/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def release_create(name: str, version: str, files: list[str] | None = None,
                   rollout_percent: int = 100, description: str = "") -> dict:
    """Create a release with optional gray rollout percentage."""
    release = {
        "id": f"{name}-{version}",
        "name": name,
        "version": version,
        "files": files or [],
        "rollout_percent": rollout_percent,
        "status": "created",
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rollout_history": [],
    }
    # Backup files
    for f in files or []:
        src = Path(f)
        if src.exists():
            backup = BACKUP_DIR / f"{release['id']}" / src.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, backup)
    (RELEASES_DIR / f"{release['id']}.json").write_text(
        json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return release


def release_rollout(release_id: str, percent: int | None = None) -> dict:
    """Rollout a release to a percentage of users."""
    path = RELEASES_DIR / f"{release_id}.json"
    if not path.exists():
        return {"error": f"Release {release_id} not found"}
    release = json.loads(path.read_text(encoding="utf-8"))
    pct = percent if percent is not None else release.get("rollout_percent", 100)
    release["status"] = "rolling_out" if pct < 100 else "deployed"
    release["rollout_percent"] = pct
    release["rollout_history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "percent": pct,
        "action": f"rolled out to {pct}%"
    })
    release["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8")
    return release


def release_rollback(release_id: str) -> dict:
    """Rollback to the previous version — restores files from backup."""
    path = RELEASES_DIR / f"{release_id}.json"
    if not path.exists():
        return {"error": f"Release {release_id} not found"}
    release = json.loads(path.read_text(encoding="utf-8"))

    # Restore files from backup
    backup_dir = BACKUP_DIR / release_id
    restored = []
    if backup_dir.exists():
        for f in backup_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, Path.cwd() / f.name)
                restored.append(f.name)
    release["status"] = "rolled_back"
    release["rollout_history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"rolled back, restored {len(restored)} files"
    })
    release["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8")
    return release


def release_list(status: str | None = None) -> list[dict]:
    """List releases."""
    result = []
    for p in sorted(RELEASES_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        if status and r.get("status") != status:
            continue
        result.append({"id": r["id"], "name": r["name"], "version": r["version"], "status": r["status"], "rollout": r.get("rollout_percent", 0)})
    return result


RELEASE_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "release_create", "description": "Create a release with backup and rollout control.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "version": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "rollout_percent": {"type": "integer", "description": "0-100"},
            "description": {"type": "string"}
        }, "required": ["name", "version"]}
    }},
    {"type": "function", "function": {
        "name": "release_rollout", "description": "Rollout release to a percentage.",
        "parameters": {"type": "object", "properties": {
            "release_id": {"type": "string"}, "percent": {"type": "integer"}
        }, "required": ["release_id"]}
    }},
    {"type": "function", "function": {
        "name": "release_rollback", "description": "Rollback to previous version.",
        "parameters": {"type": "object", "properties": {
            "release_id": {"type": "string"}
        }, "required": ["release_id"]}
    }},
    {"type": "function", "function": {
        "name": "release_list", "description": "List releases.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string"}
        }}
    }},
]

RELEASE_EXECUTOR_MAP = {
    "release_create": lambda **kw: json.dumps(release_create(**kw)),
    "release_rollout": lambda **kw: json.dumps(release_rollout(**kw)),
    "release_rollback": lambda **kw: json.dumps(release_rollback(**kw.get("release_id", ""))),
    "release_list": lambda **kw: json.dumps(release_list(kw.get("status"))),
}
