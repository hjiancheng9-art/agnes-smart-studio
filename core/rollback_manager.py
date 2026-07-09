"""
Rollback Manager — CRUX 回滚与事务管理
========================================
支持文件操作的"工具级事务"：写文件前备份 → 失败时自动回滚。
也支持学习补丁的灰度发布：先小范围应用 → 观察效果 → 全量/回滚。

功能:
1. FileTransaction: 文件事务 — 备份 → 写入 → 提交/回滚
2. RollbackManager: 回滚管理器 — 管理所有事务
3. PatchGradualRelease: 学习补丁灰度发布
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileBackup:
    """文件备份记录"""
    file_path: str
    backup_path: str
    original_hash: str
    timestamp: float = 0.0
    size: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class FileTransaction:
    """文件事务 — 写文件前自动备份，失败时自动回滚"""

    BACKUP_DIR = Path.home() / ".crux" / "rollback"

    def __init__(self):
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        self._backups: list[FileBackup] = []
        self._committed: bool = False
        self._rolled_back: bool = False

    def backup(self, file_path: str | Path) -> bool:
        """备份文件（写入前调用）"""
        path = Path(file_path)
        if not path.exists():
            return False  # 新文件无需备份

        # 计算文件哈希
        content = path.read_bytes()
        file_hash = hashlib.md5(content).hexdigest()

        # 生成备份路径
        backup_name = f"{path.name}.{str(uuid.uuid4())[:8]}.bak"
        backup_path = self.BACKUP_DIR / backup_name

        # 复制备份
        shutil.copy2(str(path), str(backup_path))

        self._backups.append(FileBackup(
            file_path=str(path),
            backup_path=str(backup_path),
            original_hash=file_hash,
            size=len(content),
        ))
        return True

    def commit(self) -> list[FileBackup]:
        """提交事务 — 清除备份"""
        self._committed = True
        backups = list(self._backups)
        for b in backups:
            try:
                if os.path.exists(b.backup_path):
                    os.remove(b.backup_path)
            except OSError:
                pass
        self._backups.clear()
        return backups

    def rollback(self) -> list[FileBackup]:
        """回滚事务 — 恢复所有备份文件"""
        self._rolled_back = True
        restored: list[FileBackup] = []

        for b in reversed(self._backups):
            try:
                if os.path.exists(b.backup_path):
                    shutil.copy2(b.backup_path, b.file_path)
                    os.remove(b.backup_path)
                    restored.append(b)
                    logger.info(f"Rollback: 恢复 {b.file_path} <- {b.backup_path}")
                else:
                    logger.warning(f"Rollback: 备份文件不存在 {b.backup_path}")
            except OSError as e:
                logger.error(f"Rollback 失败: {b.file_path}: {e}")

        self._backups.clear()
        return restored

    def get_pending_count(self) -> int:
        return len(self._backups)


class RollbackManager:
    """回滚管理器 — 管理所有文件事务"""

    def __init__(self):
        self._transactions: dict[str, FileTransaction] = {}
        self._history: list[dict[str, Any]] = []

    def begin(self, name: str = "") -> str:
        """开启新事务"""
        txn_id = f"txn_{str(uuid.uuid4())[:8]}"
        self._transactions[txn_id] = FileTransaction()
        return txn_id

    def get(self, txn_id: str) -> FileTransaction | None:
        return self._transactions.get(txn_id)

    def backup(self, txn_id: str, file_path: str | Path) -> bool:
        txn = self.get(txn_id)
        if txn:
            return txn.backup(file_path)
        return False

    def commit(self, txn_id: str) -> bool:
        """提交事务"""
        txn = self.get(txn_id)
        if not txn:
            return False
        backups = txn.commit()
        self._history.append({
            "txn_id": txn_id,
            "action": "commit",
            "files": [b.file_path for b in backups],
            "timestamp": time.time(),
        })
        del self._transactions[txn_id]
        return True

    def rollback(self, txn_id: str) -> bool:
        """回滚事务"""
        txn = self.get(txn_id)
        if not txn:
            return False
        restored = txn.rollback()
        self._history.append({
            "txn_id": txn_id,
            "action": "rollback",
            "files": [b.file_path for b in restored],
            "timestamp": time.time(),
        })
        del self._transactions[txn_id]
        return True

    def rollback_all(self) -> int:
        """回滚所有未提交事务"""
        count = 0
        for txn_id in list(self._transactions.keys()):
            if self.rollback(txn_id):
                count += 1
        return count

    def get_active_count(self) -> int:
        return len(self._transactions)

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._history[-limit:]

    def cleanup(self, max_age: float = 86400) -> int:
        """清理过期备份文件"""
        now = time.time()
        count = 0
        for f in self.BACKUP_DIR.glob("*.bak"):
            if now - f.stat().st_mtime > max_age:
                try:
                    f.unlink()
                    count += 1
                except OSError:
                    pass
        return count


@dataclass
class PatchExperiment:
    """学习补丁实验"""
    patch_id: str
    patch: dict[str, Any]
    description: str
    status: str = "pending"  # pending / testing / rolled_out / rolled_back
    test_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total * 100 if total > 0 else 0.0

    @property
    def should_rollout(self) -> bool:
        return self.test_count >= 3 and self.success_rate >= 70.0

    @property
    def should_rollback(self) -> bool:
        return self.test_count >= 3 and self.success_rate < 50.0


class GradualRelease:
    """学习补丁灰度发布"""

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            config_path = Path.home() / ".crux" / "patch_experiments.json"
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._experiments: list[PatchExperiment] = self._load()

    def _load(self) -> list[PatchExperiment]:
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text())
                return [PatchExperiment(**d) for d in data]
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        return []

    def _save(self) -> None:
        try:
            data = [{
                "patch_id": e.patch_id,
                "patch": e.patch,
                "description": e.description,
                "status": e.status,
                "test_count": e.test_count,
                "success_count": e.success_count,
                "failure_count": e.failure_count,
                "created_at": e.created_at,
            } for e in self._experiments]
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"GradualRelease 保存失败: {e}")

    def start_experiment(self, patch: dict[str, Any], description: str) -> str:
        """开始灰度实验"""
        exp = PatchExperiment(
            patch_id=f"patch_{str(uuid.uuid4())[:8]}",
            patch=patch,
            description=description,
        )
        self._experiments.append(exp)
        self._save()
        return exp.patch_id

    def record_result(self, patch_id: str, success: bool) -> None:
        """记录实验结果"""
        for exp in self._experiments:
            if exp.patch_id == patch_id:
                exp.test_count += 1
                if success:
                    exp.success_count += 1
                else:
                    exp.failure_count += 1
                if exp.should_rollout:
                    exp.status = "rolled_out"
                elif exp.should_rollback:
                    exp.status = "rolled_back"
                self._save()
                return

    def get_active_experiments(self) -> list[PatchExperiment]:
        return [e for e in self._experiments if e.status in ("pending", "testing")]

    def get_ready_patches(self) -> list[PatchExperiment]:
        """获取可以全量发布的补丁"""
        return [e for e in self._experiments if e.status == "rolled_out"]

    def get_failed_patches(self) -> list[PatchExperiment]:
        """获取需要回滚的补丁"""
        return [e for e in self._experiments if e.status == "rolled_back"]

    def get_all(self) -> list[PatchExperiment]:
        return list(self._experiments)

    def clear(self) -> None:
        self._experiments.clear()
        self._save()
