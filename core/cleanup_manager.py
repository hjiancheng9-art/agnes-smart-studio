"""CRUX 文件清理治理模块 — 扫描 / 分级 / 保护检查 / 风险评分 / 归档 / 延迟删除

设计原则:
- 不直接删除，先移入 .crux/trash/
- 每次清理前必须 dry-run 输出报告
- 三层保护: 白名单 → 引用检查 → 风险评分
- 所有操作记录到 event_log
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from core.error_sink import catch

# ═══════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════

@dataclass
class ScannedFile:
    """单个扫描结果"""
    path: Path
    size_bytes: int
    mtime: float                 # 最后修改时间戳
    extension: str               # 小写扩展名，如 ".py"
    tier: str = "unknown"        # T0 ~ T4
    rule: str = ""               # 匹配的清理规则名
    risk: str = "unknown"        # low / medium / high / protected
    reason: str = ""             # 为什么归到这个 tier
    age_days: float = 0.0        # 文件年龄（天）
    is_git_tracked: bool = False


@dataclass
class CleanupReport:
    """清理报告"""
    run_id: str
    timestamp: str
    mode: str                              # dry_run / execute
    total_scanned: int = 0
    total_size_bytes: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)
    by_rule: dict[str, int] = field(default_factory=dict)
    files_to_clean: list[ScannedFile] = field(default_factory=list)
    protected_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class TrashEntry:
    """回收站条目"""
    id: str
    original_path: str
    trashed_at: str
    size_bytes: int
    rule: str
    reason: str


# ═══════════════════════════════════════════════════════════
# Cleanup Manager
# ═══════════════════════════════════════════════════════════

class CleanupManager:
    """项目文件清理治理模块

    用法:
        mgr = CleanupManager()
        report = mgr.scan()          # 扫描并分级
        mgr.dry_run(report)          # 预览
        mgr.execute(report)          # 执行清理
        mgr.restore(entry_id)        # 恢复
    """

    def __init__(self, root: str | Path = ".", policy_path: str | None = None):
        self.root = Path(root).resolve()
        self.policy_path = Path(policy_path) if policy_path else self.root / ".crux" / "cleanup" / "policy.yaml"
        self.trash_dir = self.root / ".crux" / "trash"
        self.log_db = self.root / ".crux" / "cleanup" / "event_log.sqlite"
        self.allowlist_path = self.root / ".crux" / "cleanup" / "allowlist.txt"
        self.denylist_path = self.root / ".crux" / "cleanup" / "denylist.txt"
        self.reports_dir = self.root / ".crux" / "cleanup" / "reports"

        self._ensure_dirs()
        self._ensure_db()

        self.policy = self._load_policy()
        self._allowlist = self._load_patterns(self.allowlist_path)
        self._denylist = self._load_patterns(self.denylist_path)

        # 扫描超大型目录时跳过
        self._skip_dirs = {
            '.git', 'node_modules', '__pycache__', '.venv', 'venv',
            '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox',
            'dist', 'build', '.egg-info', '.next', '.nuxt',
            'bower_components', 'vendor',
        }

    # ── 内部工具 ──────────────────────────────────────────

    def _ensure_dirs(self):
        for d in [self.trash_dir, self.log_db.parent, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _ensure_db(self):
        conn = sqlite3.connect(str(self.log_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,       -- scan / trash / restore / permadelete
                original_path TEXT,
                trashed_path TEXT,
                size_bytes INTEGER,
                rule TEXT,
                tier TEXT,
                risk TEXT,
                reason TEXT,
                checksum TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trash_index (
                id TEXT PRIMARY KEY,
                original_path TEXT NOT NULL,
                trashed_path TEXT NOT NULL,
                trashed_at TEXT NOT NULL,
                size_bytes INTEGER,
                rule TEXT,
                reason TEXT,
                checksum TEXT,
                expires_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _load_policy(self) -> dict:
        if not self.policy_path.exists():
            return {}
        with open(self.policy_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_patterns(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        lines = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
        return lines

    def _matches_glob(self, rel_path: str, pattern: str) -> bool:
        """支持 ** 递归匹配（含直接子文件）"""
        rel = rel_path.replace("\\", "/")
        pat = pattern.replace("\\", "/")

        # 1. fnmatch 快速匹配（不含 ** 的场景）
        if "**" not in pat:
            return fnmatch.fnmatch(rel, pat)

        # 2. pathlib PurePosixPath 匹配（处理 ** 递归）
        p = PurePosixPath(rel)
        if p.match(pat):
            return True

        # 3. 对于 output/**/*.txt 这种模式，还需要匹配直接子文件
        #    pathlib 的 match() 对 ** 只匹配嵌套不匹配直接子文件
        #    所以补一个 `*` 版本
        alt_pat = pat.replace("**/*", "*")
        if alt_pat != pat and fnmatch.fnmatch(rel, alt_pat):
            return True

        # 4. 对于 **/ 开头的全局模式
        if pat.startswith("**/"):
            base = pat[3:]  # 去掉 **/
            if fnmatch.fnmatch(rel, base) or fnmatch.fnmatch(rel, "*/" + base):
                return True

        return False

    def _file_checksum(self, path: Path) -> str:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _load_git_tracked_set(self) -> set[str] | None:
        """一次性加载所有 git tracked 文件到集合，避免逐文件调用子进程"""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(self.root), capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return set(result.stdout.strip().split("\n"))
        except Exception as _es:
            catch(_es, "core.cleanup_manager", "swallowed")
        return None

    def _is_git_tracked(self, rel_path: str, git_set: set[str] | None = None) -> bool:
        """检查文件是否被 git 追踪。优先用预加载的 set"""
        if git_set is not None:
            return rel_path.replace("\\", "/") in git_set
        # fallback
        try:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", rel_path],
                cwd=str(self.root), capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _file_age_days(self, mtime: float) -> float:
        return (time.time() - mtime) / 86400.0

    # ── 保护检查 ──────────────────────────────────────────

    def _is_protected_path(self, rel_path: str) -> tuple[bool, str]:
        """检查文件是否在受保护路径内。返回 (是否受保护, 原因)"""
        protected_paths = self.policy.get("protected", {}).get("paths", [])

        for pattern in protected_paths:
            if self._matches_glob(rel_path, pattern):
                return True, f"matches protected path: {pattern}"

        return False, ""

    def _is_protected_ext(self, ext: str) -> tuple[bool, str]:
        """基于扩展名检查是否受保护"""
        protected_exts = self.policy.get("protected", {}).get("extensions", [])
        if ext.lower() in [e.lower() for e in protected_exts]:
            return True, f"protected extension: {ext}"
        return False, ""

    def _is_denylisted(self, rel_path: str) -> tuple[bool, str]:
        """强制清理列表"""
        for pattern in self._denylist:
            if self._matches_glob(rel_path, pattern):
                return True, f"matches denylist: {pattern}"
        return False, ""

    def _is_allowlisted(self, rel_path: str) -> tuple[bool, str]:
        """跳过清理的例外"""
        for pattern in self._allowlist:
            if self._matches_glob(rel_path, pattern):
                return True, f"matches allowlist: {pattern}"
        return False, ""

    # ── 分类引擎 ──────────────────────────────────────────

    def _classify(self, sf: ScannedFile) -> ScannedFile:
        """根据 policy 规则分类文件"""
        rel = str(sf.path.relative_to(self.root))

        # 1. 检查 denylist（强制清理，覆盖一切）
        is_deny, reason = self._is_denylisted(rel)
        if is_deny:
            sf.tier = "T4"
            sf.risk = "low"
            sf.reason = reason
            return sf

        # 2. 检查 allowlist（跳过清理）
        is_allow, reason = self._is_allowlisted(rel)
        if is_allow:
            sf.tier = "T0"
            sf.risk = "protected"
            sf.reason = reason
            return sf

        # 3. 检查 protected paths（T0）
        is_prot, reason = self._is_protected_path(rel)
        if is_prot:
            sf.tier = "T0"
            sf.risk = "protected"
            sf.reason = reason
            return sf

        # 4. 检查 protected extensions（核心源码也保护）
        is_pext, reason = self._is_protected_ext(sf.extension)
        if is_pext and not rel.startswith("output/") and not rel.startswith(".crux/"):
            sf.tier = "T0"
            sf.risk = "protected"
            sf.reason = reason
            sf.rule = "protected_extension"
            return sf

        # 5. 匹配 cleanup_rules
        rules = self.policy.get("cleanup_rules", {})
        for rule_name, rule_def in rules.items():
            for pattern in rule_def.get("patterns", []):
                if self._matches_glob(rel, pattern):
                    min_age = rule_def.get("min_age_days", 0)
                    if sf.age_days >= min_age:
                        sf.tier = self._rule_to_tier(rule_def)
                        sf.risk = rule_def.get("risk", "low")
                        sf.rule = rule_name
                        sf.reason = f"rule '{rule_name}' matched (age {sf.age_days:.1f}d >= {min_age}d)"
                        return sf
                    else:
                        sf.tier = "T3"
                        sf.risk = "low"
                        sf.rule = rule_name
                        sf.reason = f"rule '{rule_name}' matched but too young ({sf.age_days:.1f}d < {min_age}d)"
                        return sf

        # 6. 落在 output/ 或 .crux/ 下的未知文件 → T1
        if rel.startswith("output/") or rel.startswith(".crux/"):
            sf.tier = "T1"
            sf.risk = "low"
            sf.reason = "in output/crux directory, likely regenerable"
            return sf

        # 7. 默认：不归类，保守处理
        sf.tier = "unknown"
        sf.risk = "medium"
        sf.reason = "no rule matched — manual review recommended"
        return sf

    @staticmethod
    def _rule_to_tier(rule_def: dict) -> str:
        action = rule_def.get("action", "review")
        risk = rule_def.get("risk", "low")
        if risk == "low" and action == "trash":
            return "T4"
        elif risk == "low" and action == "review":
            return "T3"
        elif risk == "medium":
            return "T2"
        else:
            return "T1"

    # ── 扫描 ──────────────────────────────────────────────

    def scan(self, paths: list[str] | None = None, max_files: int = 5000) -> CleanupReport:
        """扫描项目文件，返回分级报告"""
        run_id = f"scan_{int(time.time())}"
        report = CleanupReport(
            run_id=run_id,
            timestamp=datetime.datetime.now().isoformat(),
            mode="scan",
        )

        scan_roots = [self.root / p for p in paths] if paths else [self.root]
        t0 = time.time()

        # 预加载 git tracked 文件集，避免逐文件调用子进程
        git_set = self._load_git_tracked_set()
        if git_set:
            print(f"  git tracked: {len(git_set)} files preloaded")

        for scan_root in scan_roots:
            for dirpath, dirnames, filenames in os.walk(scan_root):
                # 跳过不需要的目录
                dirnames[:] = [d for d in dirnames if d not in self._skip_dirs]

                rel_dir = str(Path(dirpath).relative_to(self.root))
                if rel_dir.startswith(".git"):  # 彻底跳过 .git
                    continue

                for fname in filenames:
                    if report.total_scanned >= max_files:
                        break

                    fpath = Path(dirpath) / fname
                    try:
                        stat = fpath.stat()
                    except OSError:
                        continue

                    sf = ScannedFile(
                        path=fpath,
                        size_bytes=stat.st_size,
                        mtime=stat.st_mtime,
                        extension=fpath.suffix.lower(),
                        age_days=self._file_age_days(stat.st_mtime),
                        is_git_tracked=self._is_git_tracked(str(fpath.relative_to(self.root)), git_set),
                    )

                    sf = self._classify(sf)
                    report.total_scanned += 1
                    report.total_size_bytes += sf.size_bytes
                    report.by_tier[sf.tier] = report.by_tier.get(sf.tier, 0) + 1
                    if sf.rule:
                        report.by_rule[sf.rule] = report.by_rule.get(sf.rule, 0) + 1

                    # 只收集可清理的
                    if sf.tier in ("T1", "T2", "T3", "T4"):
                        report.files_to_clean.append(sf)
                    elif sf.tier in ("T0",):
                        report.protected_skipped += 1

        report.duration_seconds = time.time() - t0
        self._log_scan(report)
        return report

    def _log_scan(self, report: CleanupReport):
        try:
            conn = sqlite3.connect(str(self.log_db))
            conn.execute(
                "INSERT INTO event_log (run_id, timestamp, action, rule, reason) VALUES (?, ?, ?, ?, ?)",
                (report.run_id, report.timestamp, "scan", "", f"scanned {report.total_scanned} files"),
            )
            conn.commit()
            conn.close()
        except Exception as _es:
            catch(_es, "core.cleanup_manager", "swallowed")

    # ── Dry-run 报告 ──────────────────────────────────────

    def dry_run(self, report: CleanupReport):
        """输出清理预览"""
        print(self._format_report(report))

    def _format_report(self, report: CleanupReport) -> str:
        lines = []
        lines.append("╔" + "═" * 68 + "╗")
        lines.append(f"║  🧹 CRUX Cleanup Report — {report.mode.upper()} {' ' * 41}║")
        lines.append("╠" + "═" * 68 + "╣")
        lines.append(f"║  Run ID:    {report.run_id:<52s}║")
        lines.append(f"║  Time:      {report.timestamp:<52s}║")
        lines.append(f"║  Scanned:   {report.total_scanned:>5d} files, {self._fmt_size(report.total_size_bytes):>8s}       ║")
        lines.append(f"║  Duration:  {report.duration_seconds:.2f}s {' ' * 53}║")
        lines.append("╠" + "═" * 68 + "╣")

        # 分级统计
        tier_order = ["T0", "T1", "T2", "T3", "T4", "unknown"]
        tier_labels = {
            "T0": "🔒 Protected",
            "T1": "📦 Regenerable",
            "T2": "🗄️  Archivable",
            "T3": "📋 Cache/Garbage",
            "T4": "🗑️  Trash",
            "unknown": "❓ Unknown",
        }
        for tier in tier_order:
            count = report.by_tier.get(tier, 0)
            if count:
                label = tier_labels.get(tier, tier)
                lines.append(f"║  {label:<18s} {count:>6d} files {' ' * 38}║")

        lines.append("╠" + "═" * 68 + "╣")

        if report.files_to_clean:
            total_cleanable = sum(f.size_bytes for f in report.files_to_clean)
            lines.append(f"║  🎯 Cleanable:  {len(report.files_to_clean):>5d} files, {self._fmt_size(total_cleanable):>8s}       ║")
            lines.append("╠" + "═" * 68 + "╣")

            # 按规则分组
            by_rule: dict[str, list[ScannedFile]] = {}
            for sf in report.files_to_clean:
                rule = sf.rule or "no_rule"
                by_rule.setdefault(rule, []).append(sf)

            for rule_name, files in sorted(by_rule.items(), key=lambda x: -len(x[1])):
                total = sum(f.size_bytes for f in files)
                lines.append(f"║  ├─ {rule_name:<30s} {len(files):>4d} files / {self._fmt_size(total):>8s}  ║")

            lines.append("╠" + "═" * 68 + "╣")

            # 列出具体文件（最多 20 个）
            shown = 0
            for sf in sorted(report.files_to_clean, key=lambda f: -f.size_bytes):
                if shown >= 20:
                    break
                rel = str(sf.path.relative_to(self.root))
                lines.append(f"║  [{sf.tier}] {self._trunc(rel, 50):<50s} {self._fmt_size(sf.size_bytes):>8s}  ║")
                shown += 1

            remaining = len(report.files_to_clean) - 20
            if remaining > 0:
                lines.append(f"║  ... and {remaining} more files {' ' * 47}║")

        lines.append("╚" + "═" * 68 + "╝")
        return "\n".join(lines)

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def _trunc(s: str, max_len: int) -> str:
        if len(s) <= max_len:
            return s
        return s[:max_len - 3] + "..."

    # ── 执行清理 ──────────────────────────────────────────

    def execute(self, report: CleanupReport, auto_confirm: bool = False) -> CleanupReport:
        """执行清理：将所有可清理文件移入 trash"""
        report.mode = "execute"
        report.errors = []

        if not auto_confirm:
            print(self._format_report(report))
            print(f"\n⚠️  确认执行清理？这将移动 {len(report.files_to_clean)} 个文件到 .crux/trash/")
            resp = input("输入 'yes' 确认: ").strip()
            if resp.lower() != "yes":
                print("❌ 已取消。")
                report.mode = "cancelled"
                return report

        moved_count = 0
        for sf in report.files_to_clean:
            try:
                self._move_to_trash(sf)
                moved_count += 1
            except Exception as e:
                report.errors.append(f"{sf.path}: {e}")

        # 清理过期 trash
        self._purge_expired_trash()

        report.duration_seconds = time.time() - time.mktime(
            time.strptime(report.timestamp, "%Y-%m-%dT%H:%M:%S.%f")
        )

        # 记录到 event log
        self._log_execute(report, moved_count)
        self._save_report(report)

        print(f"✅ 已移动 {moved_count} 个文件到 .crux/trash/")
        if report.errors:
            print(f"⚠️  {len(report.errors)} 个错误")
        return report

    def _move_to_trash(self, sf: ScannedFile) -> TrashEntry:
        entry_id = f"trash_{int(time.time())}_{hashlib.md5(str(sf.path).encode()).hexdigest()[:8]}"
        rel = str(sf.path.relative_to(self.root)).replace("\\", "/")
        trashed_path = self.trash_dir / f"{entry_id}_{Path(rel).name}"

        checksum = self._file_checksum(sf.path)
        now = datetime.datetime.now().isoformat()
        retention_days = self.policy.get("trash", {}).get("retention_days", 7)
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=retention_days)).isoformat()

        entry = TrashEntry(
            id=entry_id,
            original_path=str(sf.path),
            trashed_at=now,
            size_bytes=sf.size_bytes,
            rule=sf.rule,
            reason=sf.reason,
        )

        # 移动文件
        trashed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sf.path), str(trashed_path))

        # 记录到数据库
        conn = sqlite3.connect(str(self.log_db))
        conn.execute(
            """INSERT INTO event_log (run_id, timestamp, action, original_path, trashed_path,
               size_bytes, rule, tier, risk, reason, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("trash_" + entry.id, now, "trash", entry.original_path, str(trashed_path),
             sf.size_bytes, sf.rule, sf.tier, sf.risk, sf.reason, checksum),
        )
        conn.execute(
            """INSERT INTO trash_index (id, original_path, trashed_path, trashed_at,
               size_bytes, rule, reason, checksum, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.id, entry.original_path, str(trashed_path), now,
             sf.size_bytes, sf.rule, sf.reason, checksum, expires_at),
        )
        conn.commit()
        conn.close()

        return entry

    def _purge_expired_trash(self):
        """删除过期的 trash 条目"""
        now = datetime.datetime.now().isoformat()
        conn = sqlite3.connect(str(self.log_db))
        rows = conn.execute(
            "SELECT id, trashed_path FROM trash_index WHERE expires_at < ?", (now,)
        ).fetchall()

        purged = 0
        for row in rows:
            entry_id, trashed_path = row
            path = Path(trashed_path)
            try:
                if path.is_file():
                    path.unlink()
                    purged += 1
                elif path.is_dir():
                    shutil.rmtree(path)
                    purged += 1
                conn.execute("DELETE FROM trash_index WHERE id = ?", (entry_id,))
                conn.execute(
                    "INSERT INTO event_log (run_id, timestamp, action, original_path) VALUES (?, ?, ?, ?)",
                    ("purge_" + entry_id, now, "permadelete", trashed_path),
                )
            except Exception as _es:
                catch(_es, "core.cleanup_manager", "swallowed")

        conn.commit()
        conn.close()
        if purged:
            print(f"🗑️  已永久删除 {purged} 个过期 trash 条目")

    def _log_execute(self, report: CleanupReport, moved_count: int):
        try:
            conn = sqlite3.connect(str(self.log_db))
            conn.execute(
                "INSERT INTO event_log (run_id, timestamp, action, reason) VALUES (?, ?, ?, ?)",
                (report.run_id, report.timestamp, "execute", f"moved {moved_count} files"),
            )
            conn.commit()
            conn.close()
        except Exception as _es:
            catch(_es, "core.cleanup_manager", "swallowed")

    def _save_report(self, report: CleanupReport):
        report_path = self.reports_dir / f"{report.run_id}.json"
        data = {
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "mode": report.mode,
            "total_scanned": report.total_scanned,
            "total_size_bytes": report.total_size_bytes,
            "by_tier": report.by_tier,
            "by_rule": report.by_rule,
            "files_cleaned": [str(f.path.relative_to(self.root)) for f in report.files_to_clean],
            "protected_skipped": report.protected_skipped,
            "errors": report.errors,
            "duration_seconds": report.duration_seconds,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── 恢复 ──────────────────────────────────────────────

    def restore(self, entry_id: str) -> bool:
        """从 trash 恢复文件"""
        conn = sqlite3.connect(str(self.log_db))
        row = conn.execute(
            "SELECT id, original_path, trashed_path FROM trash_index WHERE id = ?", (entry_id,)
        ).fetchone()

        if not row:
            conn.close()
            print(f"❌ 未找到 trash 条目: {entry_id}")
            return False

        _, original_path, trashed_path = row
        src = Path(trashed_path)
        dst = Path(original_path)

        if not src.exists():
            conn.close()
            print(f"❌ Trash 文件已不存在: {trashed_path}")
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)

        # 如果目标已存在，自动重命名
        if dst.exists():
            dst = dst.with_suffix(dst.suffix + ".restored")

        shutil.move(str(src), str(dst))

        conn.execute("DELETE FROM trash_index WHERE id = ?", (entry_id,))
        conn.execute(
            "INSERT INTO event_log (run_id, timestamp, action, original_path, trashed_path) VALUES (?, ?, ?, ?, ?)",
            ("restore_" + entry_id, datetime.datetime.now().isoformat(), "restore", original_path, trashed_path),
        )
        conn.commit()
        conn.close()

        print(f"✅ 已恢复: {original_path}")
        return True

    def list_trash(self) -> list[dict]:
        """列出所有 trash 条目"""
        conn = sqlite3.connect(str(self.log_db))
        rows = conn.execute(
            "SELECT id, original_path, size_bytes, trashed_at, rule, expires_at FROM trash_index ORDER BY trashed_at DESC"
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            entry_id, orig, size, trashed_at, rule, expires = row
            remaining_days = (datetime.datetime.fromisoformat(expires) - datetime.datetime.now()).days
            results.append({
                "id": entry_id,
                "original_path": orig,
                "size_bytes": size,
                "size": self._fmt_size(size),
                "trashed_at": trashed_at,
                "rule": rule,
                "expires_in_days": max(0, remaining_days),
                "status": "expired" if remaining_days <= 0 else "active",
            })

        return results

    def show_trash(self):
        """展示回收站"""
        entries = self.list_trash()
        if not entries:
            print("📭 回收站为空。")
            return

        print("╔" + "═" * 70 + "╗")
        print(f"║  🗑️  Trash ({len(entries)} items) {' ' * 50}║")
        print("╠" + "═" * 70 + "╣")
        total_size = 0
        for e in entries:
            total_size += e["size_bytes"]
            status = "⏳" if e["status"] == "active" else "💀"
            print(f"║  {status} [{e['id'][:16]}] {self._trunc(e['original_path'], 32):<32s} {e['size']:>10s}  {e['expires_in_days']}d left  ║")
        print("╠" + "═" * 70 + "╣")
        print(f"║  Total: {self._fmt_size(total_size):>10s} {' ' * 53}║")
        print("╚" + "═" * 70 + "╝")

    # ── 快捷入口 ──────────────────────────────────────────

    def quick_clean(self, dry: bool = True) -> CleanupReport:
        """一键扫描 + 预览/执行"""
        print("🔍 扫描项目文件...")
        report = self.scan()
        if dry:
            self.dry_run(report)
        else:
            report = self.execute(report)
        return report

    def status(self):
        """项目文件状态概览"""
        print("🔍 快速扫描...")
        report = self.scan()
        self.dry_run(report)

        # Trash 状态
        print()
        self.show_trash()

        # 统计
        conn = sqlite3.connect(str(self.log_db))
        total_cleaned = conn.execute("SELECT COUNT(*) FROM event_log WHERE action = 'trash'").fetchone()[0]
        total_restored = conn.execute("SELECT COUNT(*) FROM event_log WHERE action = 'restore'").fetchone()[0]
        conn.close()

        print(f"\n📊 历史: 已清理 {total_cleaned} 次, 恢复 {total_restored} 次")
        print(f"📁 报告目录: {self.reports_dir}")


# ═══════════════════════════════════════════════════════════
# CLI entrypoint
# ═══════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="CRUX 文件清理治理工具")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "scan", "clean", "dry-run", "trash", "restore", "purge"])
    parser.add_argument("--root", default=".", help="项目根目录")
    parser.add_argument("--policy", help="策略文件路径")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    parser.add_argument("--id", help="trash 条目 ID（用于 restore）")

    args = parser.parse_args()
    mgr = CleanupManager(root=args.root, policy_path=args.policy)

    if args.action == "status":
        mgr.status()

    elif args.action == "scan" or args.action == "dry-run":
        report = mgr.scan()
        mgr.dry_run(report)

    elif args.action == "clean":
        report = mgr.scan()
        mgr.execute(report, auto_confirm=args.yes)

    elif args.action == "trash":
        mgr.show_trash()

    elif args.action == "restore":
        if not args.id:
            print("必须用 --id 指定要恢复的条目")
            sys.exit(1)
        mgr.restore(args.id)

    elif args.action == "purge":
        mgr._purge_expired_trash()
        print("✅ 已清理过期 trash")


if __name__ == "__main__":
    main()
