"""Artifact Pipeline — 制品管理与环境提升

方法论第13章: 构建制品存储、多环境提升、版本追踪。
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ARTIFACTS_DIR = Path("output/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

STAGES = ["dev", "staging", "prod"]


def artifact_store(build_id: str, files: list[str], metadata: dict | None = None) -> dict:
    """Store build artifacts with metadata."""
    record = {
        "build_id": build_id,
        "stage": "dev",
        "files": {},
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "promoted_at": None,
    }
    for f in files:
        src = Path(f)
        if src.exists():
            dest = ARTIFACTS_DIR / build_id / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            record["files"][src.name] = str(dest)
    (ARTIFACTS_DIR / f"{build_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def artifact_list(build_id: str | None = None) -> list[dict]:
    """List artifacts, optionally filtered by build."""
    result = []
    for p in sorted(ARTIFACTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == "_index.json":
            continue
        art = json.loads(p.read_text(encoding="utf-8"))
        if build_id and art.get("build_id") != build_id:
            continue
        result.append(art)
    return result


def artifact_promote(artifact_id: str, stage: str) -> dict:
    """Promote an artifact to a higher environment stage (dev → staging → prod)."""
    if stage not in STAGES:
        return {"error": f"Invalid stage: {stage}. Use: {STAGES}"}
    path = ARTIFACTS_DIR / f"{artifact_id}.json"
    if not path.exists():
        return {"error": f"Artifact {artifact_id} not found"}
    art = json.loads(path.read_text(encoding="utf-8"))
    old_stage = art.get("stage", "dev")
    if STAGES.index(stage) <= STAGES.index(old_stage):
        return {"error": f"Cannot promote from {old_stage} to {stage} (must be higher)"}
    art["stage"] = stage
    art["promoted_at"] = datetime.now(timezone.utc).isoformat()
    art["promoted_from"] = old_stage
    path.write_text(json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8")
    return art


ARTIFACT_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "artifact_store",
            "description": "Store build artifacts with metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "build_id": {"type": "string"},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["build_id", "files"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "artifact_list",
            "description": "List stored artifacts.",
            "parameters": {"type": "object", "properties": {"build_id": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "artifact_promote",
            "description": "Promote artifact across dev/staging/prod.",
            "parameters": {
                "type": "object",
                "properties": {"artifact_id": {"type": "string"}, "stage": {"type": "string", "enum": STAGES}},
                "required": ["artifact_id", "stage"],
            },
        },
    },
]

ARTIFACT_EXECUTOR_MAP = {
    "artifact_store": lambda **kw: json.dumps(artifact_store(**kw)),
    "artifact_list": lambda **kw: json.dumps(artifact_list(kw.get("build_id"))),
    "artifact_promote": lambda **kw: json.dumps(artifact_promote(**kw)),
}
