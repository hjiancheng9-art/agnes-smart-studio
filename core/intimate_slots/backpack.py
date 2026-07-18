"""行囊 · 配置快照/备份/回滚 — one-click backup & restore.
Snapshot: config files + capability state + session memory.
Rollback: restore from any timestamped snapshot.
Usage: from core.intimate_slots.backpack import backpack
backpack.snapshot()
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger("crux.backpack")
ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_DIR = ROOT / "output" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
FILES_TO_SNAPSHOT = [
    "models.json",
    "tools.json",
    "skills.json",
    "output/memory.json",
    "output/capability_state.json",
    "output/sessions.json",
]


class Backpack:
    def __init__(self):
        self._max_snapshots = 10

    def snapshot(self, label: str = "") -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        name = f"{ts}_{label}" if label else ts
        dest = SNAPSHOT_DIR / name
        dest.mkdir(exist_ok=True)
        saved = []
        for f in FILES_TO_SNAPSHOT:
            src = ROOT / f
            if not src.exists():
                continue
            dst = dest / f.replace("/", "_")
            shutil.copy2(src, dst)
            saved.append(f)
        meta = {"timestamp": ts, "label": label, "files": saved}
        (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self._prune()
        logger.debug("[行囊] snapshot %s: %d files", name, len(saved))
        return name

    def list_snapshots(self) -> list[str]:
        return sorted([d.name for d in SNAPSHOT_DIR.iterdir() if d.is_dir()], reverse=True)

    def rollback(self, snapshot_name: str) -> bool:
        src = SNAPSHOT_DIR / snapshot_name
        if not src.exists():
            return False
        # safety snapshot before rollback
        self.snapshot(f"pre_rollback_{snapshot_name}")
        for f in FILES_TO_SNAPSHOT:
            bak = src / f.replace("/", "_")
            if bak.exists():
                shutil.copy2(bak, ROOT / f)
        logger.debug("[行囊] rolled back to %s", snapshot_name)
        return True

    def _prune(self):
        snapshots = sorted(SNAPSHOT_DIR.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
        for old in snapshots[self._max_snapshots :]:
            shutil.rmtree(old, ignore_errors=True)

    def summary(self) -> str:
        snaps = self.list_snapshots()[:5]
        return f"[行囊] {len(snaps)} snapshots: {', '.join(snaps[:3])}"


backpack = Backpack()
