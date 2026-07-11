"""
CRUX 根目录自动整理
====================
扫描根目录临时文件，按内容特征分类移动到对应 tmp/ 子目录。
支持按年龄自动清理旧文件。

规则来源: AGENTS.md 文件组织规范
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ── 分类规则 ──────────────────────────────────────

# (文件名匹配模式, 目标子目录, 描述)
CLASSIFY_RULES: list[tuple[Callable[[str], bool], str, str]] = [
    # CDP 浏览器碎片
    (lambda n: n.startswith("_cdp_"), "tmp/cdp_fragments", "CDP 浏览器碎片"),
    # GPT 对话导出
    (
        lambda n: any(
            n.startswith(p)
            for p in (
                "_ask_chatgpt", "_chat_full", "chatgpt_response",
            )
        ),
        "tmp/gpt_outputs",
        "GPT 对话导出",
    ),
    # CRUX / TUI 片段
    (
        lambda n: any(
            n.startswith(p) for p in ("_crux_", "_tui_", "_tui")
        ),
        "tmp/scraps",
        "CRUX/TUI 代码片段",
    ),
    # 流式传输调试
    (
        lambda n: any(
            n.startswith(p) for p in ("_send_", "_stream_")
        ),
        "tmp/scraps",
        "流式调试碎片",
    ),
    # 通用临时文件
    (
        lambda n: n.startswith("tmp_") or n.startswith("temp_"),
        "tmp/scraps",
        "通用临时文件",
    ),
    # 自动化修复/脚本
    (
        lambda n: any(
            n.startswith(p)
            for p in ("auto_fix", "run_auto", "run_smoke")
        ),
        "tmp/job_logs",
        "自动化任务脚本",
    ),
    # 日志文件
    (lambda n: n.endswith(".log"), "tmp/job_logs", "日志文件"),
    # SQLite 数据库 (在根目录)
    (lambda n: n.endswith(".sqlite") or n.endswith(".db"), "data", "数据库文件"),
    # 崩溃日志
    (lambda n: "crash" in n.lower() and n.endswith(".log"), "tmp/diagnostics", "崩溃日志"),
    # Benchmark 历史
    (lambda n: n.startswith("benchmark_") or "benchmark" in n.lower(), "tmp/diagnostics", "基准测试"),
]


@dataclass
class TidyResult:
    """单次整理结果"""

    moved: list[tuple[str, str]] = field(default_factory=list)
    """(源文件名, 目标路径)"""

    skipped: list[str] = field(default_factory=list)
    """跳过的文件（不匹配任何规则）"""

    deleted: list[str] = field(default_factory=list)
    """已删除的过期文件"""

    errors: list[tuple[str, str]] = field(default_factory=list)
    """(文件名, 错误信息)"""

    @property
    def total_actions(self) -> int:
        return len(self.moved) + len(self.deleted)

    def summary(self) -> str:
        lines = []
        if self.moved:
            lines.append(f"📦 移动 {len(self.moved)} 个文件:")
            for src, dst in self.moved:
                lines.append(f"   {src} → {dst}")
        if self.deleted:
            lines.append(f"🗑 删除 {len(self.deleted)} 个过期文件")
        if self.errors:
            lines.append(f"⚠ {len(self.errors)} 个错误:")
            for fname, err in self.errors:
                lines.append(f"   {fname}: {err}")
        if not lines:
            lines.append("✨ 根目录已整洁，无需整理")
        return "\n".join(lines)


# ── 公开 API ──────────────────────────────────────

def tidy_root(
    root: str | Path | None = None,
    *,
    dry_run: bool = False,
    delete_older_than_days: int = 0,
) -> TidyResult:
    """扫描并整理根目录临时文件。

    Args:
        root: 项目根目录，默认自动检测
        dry_run: True 时只报告，不实际移动/删除
        delete_older_than_days: > 0 时删除超过此天数的 tmp/ 旧文件

    Returns:
        TidyResult
    """
    if root is None:
        root = _find_root()
    root = Path(root)

    result = TidyResult()

    # 确保 tmp/ 子目录存在
    if not dry_run:
        _ensure_tmp_dirs(root)

    # 扫描根目录所有文件
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue

        fname = entry.name

        # 跳过已知的项目文件
        if _is_project_file(fname):
            continue

        # 跳过隐藏文件（除了已知的临时文件）
        if fname.startswith(".") and not fname.startswith("_"):
            continue

        # 匹配分类规则
        matched = False
        for predicate, target_dir, _desc in CLASSIFY_RULES:
            if predicate(fname):
                dst_dir = root / target_dir
                dst = dst_dir / fname

                # 避免覆盖: 如果目标已存在，加时间戳后缀
                if dst.exists():
                    stem = Path(fname).stem
                    suffix = Path(fname).suffix
                    ts = int(time.time())
                    dst = dst_dir / f"{stem}_{ts}{suffix}"

                if dry_run:
                    result.moved.append((fname, str(dst.relative_to(root))))
                else:
                    try:
                        shutil.move(str(entry), str(dst))
                        result.moved.append((fname, str(dst.relative_to(root))))
                    except OSError as e:
                        result.errors.append((fname, str(e)))

                matched = True
                break

        if not matched and _looks_like_temp(fname):
            # 未匹配但看起来像临时文件 → 放入 scraps
            dst_dir = root / "tmp/scraps"
            dst = dst_dir / fname
            if dst.exists():
                stem = Path(fname).stem
                suffix = Path(fname).suffix
                dst = dst_dir / f"{stem}_{int(time.time())}{suffix}"

            if dry_run:
                result.moved.append((fname, str(dst.relative_to(root))))
            else:
                try:
                    shutil.move(str(entry), str(dst))
                    result.moved.append((fname, str(dst.relative_to(root))))
                except OSError as e:
                    result.errors.append((fname, str(e)))

    # 清理 tmp/ 下的过期文件
    if delete_older_than_days > 0:
        _cleanup_old_files(root, delete_older_than_days, dry_run, result)

    return result


def tidy_on_startup(root: str | Path | None = None) -> TidyResult:
    """启动时静默整理（不删旧文件，只分类 + 确保目录结构存在）。"""
    result = tidy_root(root, dry_run=False, delete_older_than_days=0)
    _ensure_required_dirs(_find_root() if root is None else Path(root))
    return result


def deep_clean(root: str | Path | None = None, older_than_days: int = 7) -> TidyResult:
    """深度清理：分类 + 删除过期文件 + 清除 __pycache__ + 清理 .crux/。

    Args:
        older_than_days: 删除超过此天数的旧文件（默认 7 天）
    """
    if root is None:
        root = _find_root()
    root = Path(root)

    result = tidy_root(root, dry_run=False, delete_older_than_days=older_than_days)

    # 清除所有 __pycache__ 目录
    pycache_cleaned = _clean_pycache(root, dry_run=False)
    for d in pycache_cleaned:
        result.deleted.append(str(d))

    # 清理 .crux/ 子目录过期文件
    crux_cleaned = _clean_crux_dir(root, older_than_days, dry_run=False)
    result.deleted.extend(crux_cleaned)

    # 删除空目录
    _remove_empty_dirs(root, dry_run=False)

    # 确保规范目录存在
    _ensure_required_dirs(root)

    return result


def full_status(root: str | Path | None = None) -> dict:
    """完整诊断：检查所有子目录的整洁度。"""
    if root is None:
        root = _find_root()
    root = Path(root)

    status = {}

    pc = 0
    for _dirpath, dirnames, _filenames in os.walk(str(root)):
        if "__pycache__" in dirnames:
            pc += 1
    status["pycache_dirs"] = pc

    crux = root / ".crux"
    if crux.is_dir():
        for sub in sorted(crux.iterdir()):
            if sub.is_dir():
                cnt = sum(1 for _ in sub.rglob("*") if _.is_file())
                status[f"crux/{sub.name}"] = cnt

    tmp = root / "tmp"
    if tmp.is_dir():
        for sub in sorted(tmp.iterdir()):
            if sub.is_dir():
                cnt = sum(1 for _ in sub.iterdir())
                status[f"tmp/{sub.name}"] = cnt

    required = [
        "browser_sessions",
        "tmp/cdp_fragments", "tmp/gpt_outputs", "tmp/diagnostics",
        "tmp/job_logs", "tmp/workflows", "tmp/scraps",
        "output/images", "output/videos",
    ]
    status["missing_dirs"] = [d for d in required if not (root / d).is_dir()]

    return status


# ── 内部 ──────────────────────────────────────────

# 项目核心文件（不移动）
_PROJECT_FILES = frozenset({
    "crux_studio.py", "models.json", ".env", ".env.example",
    "requirements.txt", "pyproject.toml", "AGENTS.md", "AGENTS_REF.md",
    "README.md", "LICENSE", "CHANGELOG.md", "METHODOLOGY.md",
    "CLAUDE.md", "HELP.md", "settings.json", "tools.json",
    ".editorconfig", ".gitignore", ".pre-commit-config.yaml",
    ".mcp.json", "pyright_baseline.json", "crux.ico",
    "crux.bat", "crux.sh", "launch.bat", "launch.sh",
    "mcp_vision_server.py",
})


def _is_project_file(fname: str) -> bool:
    """判断是否为项目核心文件"""
    return fname in _PROJECT_FILES or fname.startswith("test_") or fname == "conftest.py"


def _looks_like_temp(fname: str) -> bool:
    """启发式判断是否像临时文件"""
    name_lower = fname.lower()
    indicators = [
        "_cdp_", "_crux_", "_tui_", "_gpt_", "_ask_", "_chat_",
        "_route_", "_send_", "_stream_", "tmp_", "temp_",
        "chatgpt_response", "benchmark",
    ]
    return any(ind in name_lower for ind in indicators)


def _find_root() -> Path:
    """自动查找项目根目录"""
    # 从当前文件位置向上找
    current = Path(__file__).resolve().parent.parent
    # 验证: 有 crux_studio.py 才是根
    if (current / "crux_studio.py").exists():
        return current
    # 兜底: 当前工作目录
    cwd = Path.cwd()
    if (cwd / "crux_studio.py").exists():
        return cwd
    return current


def _ensure_tmp_dirs(root: Path) -> None:
    """确保 tmp/ 子目录结构存在"""
    subdirs = [
        "tmp/cdp_fragments",
        "tmp/gpt_outputs",
        "tmp/diagnostics",
        "tmp/job_logs",
        "tmp/workflows",
        "tmp/scraps",
        "output/images",
        "output/videos",
    ]
    for sd in subdirs:
        (root / sd).mkdir(parents=True, exist_ok=True)


def _cleanup_old_files(
    root: Path,
    older_than_days: int,
    dry_run: bool,
    result: TidyResult,
) -> None:
    """清理 tmp/ 下超过指定天数的文件"""
    cutoff = time.time() - older_than_days * 86400
    tmp_root = root / "tmp"

    if not tmp_root.exists():
        return

    for dirpath, _dirnames, filenames in os.walk(str(tmp_root)):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                mtime = fpath.stat().st_mtime
                if mtime < cutoff:
                    if dry_run:
                        result.deleted.append(str(fpath.relative_to(root)))
                    else:
                        fpath.unlink()
                        result.deleted.append(str(fpath.relative_to(root)))
            except OSError as e:
                result.errors.append((str(fpath), str(e)))

    # 清理空目录
    if not dry_run:
        for dirpath, _dirnames, _filenames in os.walk(str(tmp_root), topdown=False):
            if dirpath == str(tmp_root):
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass


def _clean_pycache(root: Path, dry_run: bool) -> list[str]:
    """清除所有 __pycache__ 目录。返回已清理的目录路径列表。"""
    cleaned = []
    for dirpath, dirnames, _filenames in os.walk(str(root), topdown=False):
        if "__pycache__" in dirnames:
            pc_dir = Path(dirpath) / "__pycache__"
            try:
                rel = str(pc_dir.relative_to(root))
                if not dry_run:
                    shutil.rmtree(str(pc_dir))
                cleaned.append(rel)
            except OSError:
                pass
    return cleaned


def _clean_crux_dir(root: Path, older_than_days: int, dry_run: bool) -> list[str]:
    """清理 .crux/ 子目录中超过 N 天的文件。返回已删除的文件路径列表。"""
    deleted = []
    crux = root / ".crux"
    if not crux.is_dir():
        return deleted

    cutoff = time.time() - older_than_days * 86400

    # 需要清理的子目录
    clean_targets = ["trash", "benchmark_history", "cleanup", "field_sessions"]
    for target in clean_targets:
        target_dir = crux / target
        if not target_dir.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(str(target_dir)):
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    mtime = fpath.stat().st_mtime
                    if mtime < cutoff:
                        rel = str(fpath.relative_to(root))
                        if not dry_run:
                            fpath.unlink()
                        deleted.append(rel)
                except OSError:
                    pass

    # 清理空子目录
    if not dry_run:
        for target in clean_targets:
            target_dir = crux / target
            if not target_dir.is_dir():
                continue
            for dirpath, _dirnames, _filenames in os.walk(str(target_dir), topdown=False):
                if dirpath == str(target_dir):
                    continue
                try:
                    if not os.listdir(dirpath):
                        os.rmdir(dirpath)
                except OSError:
                    pass

    return deleted


def _remove_empty_dirs(root: Path, dry_run: bool) -> None:
    """删除项目中的空目录（跳过 .git, node_modules 等）。"""
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=False):
        if dirpath == str(root):
            continue
        # 跳过保护目录
        parts = Path(dirpath).relative_to(root).parts
        if any(p in skip_dirs for p in parts):
            continue
        try:
            if not os.listdir(dirpath):
                if not dry_run:
                    os.rmdir(dirpath)
        except OSError:
            pass


def _ensure_required_dirs(root: Path) -> None:
    """确保 AGENTS.md 规范要求的所有目录都存在。"""
    required = [
        "browser_sessions",
        "tmp/cdp_fragments",
        "tmp/gpt_outputs",
        "tmp/diagnostics",
        "tmp/job_logs",
        "tmp/workflows",
        "tmp/scraps",
        "output",
        "output/images",
        "output/videos",
    ]
    for d in required:
        (root / d).mkdir(parents=True, exist_ok=True)
