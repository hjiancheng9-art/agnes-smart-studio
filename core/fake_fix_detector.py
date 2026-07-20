"""Self-Heal Fake Fix Detection — 区分真修复 vs 假成功

基于 GPT 架构审计 Q1 建议：
- 仅对高风险工具做检测：patch_file, execute_plan, self_heal, pip_install
- Pre/post state checksum 对比
- 三态结果：fix-probable / fix-unknown / fix-spurious
- Spurious fix 隔离：evidence-driven exponential backoff（非固定窗口）
  - context 无变化时正常递增 backoff: 24h → 3d → 7d → 30d → 永久
  - context 有变化时降级 backoff，避免"用户改了环境还被封"

与 EventLog 集成：每次 self-heal 前后状态写入 metadata，
后续可从 event_log 查询假阳性率。
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from core.error_sink import catch

# ── High-risk tools that need fake-fix detection ──────────
HIGH_RISK_TOOLS = {"patch_file", "execute_plan", "self_heal", "pip_install"}


# ── Quarantine tracking ───────────────────────────────────
@dataclass
class QuarantineEntry:
    tool: str
    error_signature: str  # hash of error_type + key context
    first_seen: float
    retry_count: int = 0
    last_retry: float = 0.0
    context_snapshots: list[dict] = field(default_factory=list)
    quarantine_count: int = 0  # how many times re-quarantined
    backoff_level: int = 0  # 0=24h, 1=3d, 2=7d, 3=30d, 4+=permanent


_quarantine: dict[str, QuarantineEntry] = {}
MAX_RETRIES_24H = 3
QUARANTINE_WINDOW = 24 * 3600  # base: 24 hours

# Exponential backoff levels (in seconds)
BACKOFF_LEVELS = [
    24 * 3600,  # 0: 24h
    3 * 24 * 3600,  # 1: 3d
    7 * 24 * 3600,  # 2: 7d
    30 * 24 * 3600,  # 3: 30d
]  # Level 4+ = permanent (float('inf'))

# Context keys considered "stable" — if none change, backoff multiplies
CONTEXT_STABILITY_KEYS = {
    "python_version",
    "torch_version",
    "cuda_version",
    "os_type",
    "free_memory_mb",
    "free_disk_mb",
    "pip_package_count",
}


def _make_error_signature(tool: str, error_type: str, context: dict) -> str:
    """Create a stable signature for an error pattern."""
    key_parts = [
        tool,
        error_type,
        json.dumps(context, sort_keys=True, default=str),
    ]
    raw = "|".join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _capture_context_snapshot(context: dict | None = None) -> dict:
    """捕获关键系统上下文快照，用于 stability 检测。"""
    snapshot = {}
    try:
        import sys

        snapshot["python_version"] = sys.version[:30]
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")
    try:
        import os
        import shutil

        _, _, free = shutil.disk_usage(os.getcwd())
        snapshot["free_disk_mb"] = free // (1024 * 1024)
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")
    try:
        import psutil

        snapshot["free_memory_mb"] = psutil.virtual_memory().available // (1024 * 1024)
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")
    try:
        import subprocess

        r = subprocess.run(["pip", "list", "--format=columns"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")[2:]
        snapshot["pip_package_count"] = len(lines)
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")
    try:
        import torch

        snapshot["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            snapshot["cuda_version"] = torch.version.cuda or "unknown"
    except ImportError:
        pass

    if context:
        snapshot.update(context)
    return snapshot


def _get_backoff_window(entry: QuarantineEntry) -> float:
    """获取当前 backoff 级别对应的时间窗口（秒）。

    使用 exponential backoff + context stability multiplier:
    - 如果 context 稳定（无变化）→ 正常递增 backoff
    - 如果 context 变化了 → 降一级 backoff
    """
    level = entry.backoff_level

    # Context stability check: 如果 context 有变化，降一级
    if len(entry.context_snapshots) >= 2:
        last = entry.context_snapshots[-1]
        prev = entry.context_snapshots[-2]
        changes = 0
        for key in CONTEXT_STABILITY_KEYS:
            if last.get(key) != prev.get(key):
                changes += 1
        if changes > 0:
            level = max(0, level - 1)

    if level >= len(BACKOFF_LEVELS):
        return float("inf")  # 永久隔离
    return BACKOFF_LEVELS[level]


def _is_context_stable(entry: QuarantineEntry) -> bool:
    """检查最近两次 context snapshot 是否稳定（无关键变化）。"""
    if len(entry.context_snapshots) < 2:
        return True
    last = entry.context_snapshots[-1]
    prev = entry.context_snapshots[-2]
    return all(last.get(key) == prev.get(key) for key in CONTEXT_STABILITY_KEYS)


def is_quarantined(tool: str, error_type: str, context: dict | None = None) -> bool:
    """Check if this error pattern has been quarantined (evidence-driven backoff)."""
    # ── 先查种子策略 ──
    from core.fake_fix_seed_policy import get_seed_policy

    seed = get_seed_policy()
    decision = seed.classify(tool, error_type, context or {})
    if decision.action == "quarantine":
        return True
    if decision.action in ("downgrade_to_diagnosis", "requires_user_action"):
        return True

    if tool not in HIGH_RISK_TOOLS:
        return False

    sig = _make_error_signature(tool, error_type, context or {})
    entry = _quarantine.get(sig)

    if entry is None:
        return False

    # Exponential backoff: 用当前 backoff 级别决定窗口
    window = _get_backoff_window(entry)

    # 永久隔离
    if window == float("inf"):
        return True

    # Check if quarantine window has passed
    if time.time() - entry.first_seen > window:
        # 窗口过期 → 清除并允许重试（保留 quarantine_count 历史）
        del _quarantine[sig]
        return False

    # Check retry count
    seed_max = MAX_RETRIES_24H
    from core.fake_fix_seed_policy import get_seed_policy

    seed = get_seed_policy()
    decision = seed.classify(tool, error_type, context or {})
    if decision.action == "limited_retry":
        seed_max = min(decision.max_retries, MAX_RETRIES_24H)

    return entry.retry_count >= seed_max


def record_retry(tool: str, error_type: str, context: dict | None = None):
    """Record a retry attempt for quarantine tracking (with context snapshot)."""
    if tool not in HIGH_RISK_TOOLS:
        return

    sig = _make_error_signature(tool, error_type, context or {})
    now = time.time()
    ctx_snapshot = _capture_context_snapshot(context)

    if sig not in _quarantine:
        _quarantine[sig] = QuarantineEntry(
            tool=tool,
            error_signature=sig,
            first_seen=now,
            retry_count=1,
            last_retry=now,
            context_snapshots=[ctx_snapshot],
        )
    else:
        entry = _quarantine[sig]
        entry.retry_count += 1
        entry.last_retry = now

        # 存储 context snapshot（最多保留最近 5 个）
        entry.context_snapshots.append(ctx_snapshot)
        if len(entry.context_snapshots) > 5:
            entry.context_snapshots.pop(0)

        # 当 retry_count 达到上限触发隔离时，增加 quarantine_count
        seed_max = MAX_RETRIES_24H
        from core.fake_fix_seed_policy import get_seed_policy

        seed = get_seed_policy()
        decision = seed.classify(tool, error_type, context or {})
        if decision.action == "limited_retry":
            seed_max = min(decision.max_retries, MAX_RETRIES_24H)

        if entry.retry_count >= seed_max:
            entry.quarantine_count += 1
            entry.backoff_level = min(entry.quarantine_count, 5)
            # 如果 context 稳定，backoff 递增更快
            if _is_context_stable(entry) and entry.quarantine_count > 1:
                entry.backoff_level = min(entry.quarantine_count + 1, 5)
            # 重置 retry_count（为下一个窗口做准备）
            entry.retry_count = 0


# ── Pre/Post State Capture ────────────────────────────────
class StateSnapshot:
    """Captures pre- or post-execution state for comparison."""

    def __init__(self):
        self.file_hashes: dict[str, str] = {}
        self.git_diff_stat: str = ""
        self.test_results: dict[str, Any] = {}
        self.import_status: dict[str, bool] = {}
        self.timestamp: float = time.time()

    def to_dict(self) -> dict:
        return {
            "file_hashes": self.file_hashes,
            "git_diff_stat": self.git_diff_stat[:500],
            "test_results": self.test_results,
            "import_status": self.import_status,
            "timestamp": self.timestamp,
        }


def capture_pre_state(project_dir: str = ".") -> StateSnapshot:
    """Capture state before a risky operation."""
    state = StateSnapshot()

    key_patterns = ["*.py", "*.json", "*.yaml", "*.yml", "*.toml"]
    try:
        import glob as _glob

        for pattern in key_patterns:
            for fpath in _glob.glob(os.path.join(project_dir, "**", pattern), recursive=True):
                if any(skip in fpath for skip in ["__pycache__", ".git", "node_modules", "venv", ".venv"]):
                    continue
                try:
                    with open(fpath, "rb") as f:
                        state.file_hashes[fpath] = hashlib.sha256(f.read()).hexdigest()[:16]
                except (OSError, PermissionError):
                    state.file_hashes[fpath] = "ERROR:unreadable"
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")

    try:
        import subprocess

        r = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, timeout=5, cwd=project_dir)
        state.git_diff_stat = r.stdout.strip()
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")

    return state


def capture_post_state(pre_state: StateSnapshot, project_dir: str = ".") -> StateSnapshot:
    """Capture state after a risky operation."""
    post = StateSnapshot()

    try:
        for fpath in pre_state.file_hashes:
            try:
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        post.file_hashes[fpath] = hashlib.sha256(f.read()).hexdigest()[:16]
                else:
                    post.file_hashes[fpath] = "DELETED"
            except (OSError, PermissionError):
                post.file_hashes[fpath] = "ERROR:unreadable"
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")

    try:
        import subprocess

        r = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, timeout=5, cwd=project_dir)
        post.git_diff_stat = r.stdout.strip()
    except Exception as _es:
        catch(_es, "core.fake_fix_detector", "swallowed")

    return post


# ── Fix Classification ────────────────────────────────────
def classify_fix(
    tool: str,
    error_type: str,
    pre: StateSnapshot,
    post: StateSnapshot,
    test_passed: bool = False,
) -> str:
    """Classify a self-heal outcome.

    Returns:
        "fix-probable": state changed meaningfully + tests pass
        "fix-unknown": can't determine (not enough state change)
        "fix-spurious": no state change, or only ephemeral change
    """
    if tool not in HIGH_RISK_TOOLS:
        return "fix-unknown"

    changed_files = 0
    for fpath, post_hash in post.file_hashes.items():
        pre_hash = pre.file_hashes.get(fpath, "")
        if pre_hash != post_hash:
            changed_files += 1

    git_changed = pre.git_diff_stat != post.git_diff_stat and bool(post.git_diff_stat)

    if changed_files > 0 and test_passed:
        return "fix-probable"
    if (changed_files > 0 and not test_passed) or (changed_files == 0 and git_changed):
        return "fix-unknown"
    if changed_files == 0 and not git_changed:
        return "fix-spurious"
    return "fix-unknown"


def should_retry(tool: str, error_type: str, context: dict | None = None) -> dict:
    """Decision helper: should we retry this self-heal?

    Returns:
        {"retry": bool, "reason": str}
    """
    if tool not in HIGH_RISK_TOOLS:
        return {"retry": False, "reason": "not a high-risk tool"}

    # ── 先查种子策略 ──
    from core.fake_fix_seed_policy import get_seed_policy

    seed = get_seed_policy()
    decision = seed.classify(tool, error_type, context or {})
    if decision.action == "quarantine":
        return {"retry": False, "reason": f"seed policy: {decision.reason}"}
    if decision.action == "downgrade_to_diagnosis":
        return {"retry": False, "reason": f"downgraded to diagnosis: {decision.reason}"}
    if decision.action == "requires_user_action":
        return {"retry": False, "reason": f"requires user action: {decision.reason}"}

    sig = _make_error_signature(tool, error_type, context or {})
    entry = _quarantine.get(sig)

    if entry is None:
        return {"retry": True, "reason": "first attempt"}

    # Exponential backoff window check
    window = _get_backoff_window(entry)
    if window == float("inf"):
        return {"retry": False, "reason": "permanently quarantined after repeated failures"}
    if time.time() - entry.first_seen > window:
        del _quarantine[sig]
        return {"retry": True, "reason": "quarantine window expired"}

    seed_max = MAX_RETRIES_24H
    if decision.action == "limited_retry":
        seed_max = min(decision.max_retries, MAX_RETRIES_24H)

    remaining = seed_max - entry.retry_count
    if remaining > 0:
        return {"retry": True, "reason": f"{remaining} retries remaining"}
    level_name = _get_backoff_level_name(entry.backoff_level)
    return {
        "retry": False,
        "reason": f"quarantined ({level_name}): {entry.retry_count} retries, error_sig={sig}",
    }


def _get_backoff_level_name(level: int) -> str:
    names = ["24h", "3d", "7d", "30d", "permanent"]
    if level < len(names):
        return names[level]
    return "permanent"


def clear_quarantine(tool: str, error_type: str, context: dict | None = None) -> bool:
    """手动清除某个错误的隔离状态（用户解除）。"""
    sig = _make_error_signature(tool, error_type, context or {})
    if sig in _quarantine:
        del _quarantine[sig]
        return True
    return False


def reset_fake_fix_detector() -> None:
    """Reset quarantine state (for test isolation)."""
    _quarantine.clear()
