"""工具结果缓存 — 避免只读工具在同一对话轮次中被重复执行。

缓存策略：
- 文件类工具 (read_file, check_file_exists): mtime 失效 — 文件被修改后自动失效
- 目录扫描类 (search_files, glob_files, list_files, tree_dir): 短 TTL (30s)
- Git 读取类 (git_status, git_diff, git_log): 短 TTL (15s)
- 网络类 (web_fetch, web_search): 中 TTL (120s)
- 环境检测 (env_check): 长 TTL (600s)

写操作工具 (run_bash, run_python) 执行后清空整个缓存，因为它们可能修改任意文件。

线程安全：所有操作通过 threading.Lock 保护。
"""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict

__all__ = ["CACHEABLE_TOOLS", "ToolResultCache", "WRITE_TOOLS_INVALIDATE"]


# ── 可缓存工具集合 ──

CACHEABLE_TOOLS = {
    # 文件读取 — mtime 失效
    "read_file",
    # 目录扫描 — 短 TTL
    "search_files",
    "glob_files",
    "list_files",
    "tree_dir",
    # 代码统计 — 短 TTL
    "count_lines",
    # 环境检测 — 长 TTL（会话内基本不变）
    "env_check",
    # Git 只读 — 短 TTL（任何写操作都可能改变 git 状态）
    "git_status",
    "git_diff",
    "git_log",
    # 网络读取 — 中 TTL
    "web_fetch",
    "web_search",
    # 管道检查 — 短 TTL
    "check_file_exists",
    "list_project_files",
    "project_dependency_graph",
    # 模型信息 — 长 TTL
    "video_model_info",
    # 测试执行 — 中 TTL
    "run_test",
}

# 写操作工具 — 执行后触发缓存失效
WRITE_TOOLS_INVALIDATE = {
    "run_bash",
    "run_python",  # 可修改任意文件
    "write_file",
    "edit_file",  # 直接修改文件
    "git_add_commit",  # 改变 git 状态
    "pip_install",  # 改变依赖环境
    "download_file",  # 写入下载文件
}

# ── TTL 配置（秒）──

_TOOL_TTL: dict[str, float] = {}
for _t in ("read_file",):
    _TOOL_TTL[_t] = 60
for _t in ("search_files", "glob_files", "list_files", "tree_dir", "count_lines"):
    _TOOL_TTL[_t] = 30
for _t in ("git_status", "git_diff", "git_log"):
    _TOOL_TTL[_t] = 15
for _t in ("web_fetch", "web_search", "run_test"):
    _TOOL_TTL[_t] = 120
for _t in ("env_check",):
    _TOOL_TTL[_t] = 600
for _t in ("check_file_exists", "list_project_files", "project_dependency_graph"):
    _TOOL_TTL[_t] = 30
for _t in ("video_model_info",):
    _TOOL_TTL[_t] = 300
_DEFAULT_TTL = 30

# 需要 mtime 检查的工具
_MTIME_TOOLS = {"read_file", "check_file_exists"}


class ToolResultCache:
    """LRU 缓存，为只读工具结果提供 mtime/TTL 两级失效机制。

    用法:
        cache = ToolResultCache()

        # 读取
        result = cache.get("read_file", '{"path": "/tmp/a.py"}')
        if result is not None:
            return result  # 缓存命中

        # 执行后写入
        result = execute_tool(...)
        cache.put("read_file", '{"path": "/tmp/a.py"}', result)

        # 写操作后清空
        cache.invalidate_all()
    """

    def __init__(self, max_size: int = 128) -> None:
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ── 公共接口 ──

    @staticmethod
    def make_key(name: str, args_json: str) -> str:
        """生成确定性缓存键。"""
        h = hashlib.md5(args_json.encode("utf-8", errors="replace")).hexdigest()[:12]
        return f"{name}:{h}"

    def get(self, name: str, args_json: str) -> str | None:
        """查找缓存。命中返回结果字符串，未命中返回 None。"""
        key = self.make_key(name, args_json)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            # TTL 检查
            ttl = _TOOL_TTL.get(name, _DEFAULT_TTL)
            if time.time() - entry["ts"] > ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # mtime 检查（文件被外部修改则失效）
            if name in _MTIME_TOOLS and entry.get("path"):
                try:
                    if os.path.exists(entry["path"]) and os.path.getmtime(entry["path"]) != entry.get("mtime", 0):
                        del self._cache[key]
                        self._misses += 1
                        return None
                except (OSError, ValueError):
                    pass  # mtime 检查失败，保留缓存结果

            # LRU: 移到末尾
            self._cache.move_to_end(key)
            self._hits += 1
            return entry["result"]

    def put(self, name: str, args_json: str, result: str):
        """存储工具结果。错误结果不缓存。"""
        # 不缓存错误/拦截结果
        if result.startswith("[错误]") or result.startswith("[PLAN MODE]"):
            return

        key = self.make_key(name, args_json)
        entry: dict = {"result": result, "ts": time.time()}

        # 为文件类工具存储 mtime
        if name in _MTIME_TOOLS:
            try:
                args = json.loads(args_json or "{}")
                path = args.get("path", "") or args.get("file_path", "")
                if path and os.path.exists(path):
                    entry["path"] = os.path.normpath(path)
                    entry["mtime"] = os.path.getmtime(path)
            except (json.JSONDecodeError, OSError):
                pass

        with self._lock:
            # LRU 淘汰
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = entry

    def invalidate_all(self):
        """清空整个缓存。run_bash/run_python 等任意写操作后调用。"""
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> dict:
        """缓存统计信息。"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 2) if total > 0 else 0.0,
            }

    def __repr__(self) -> str:
        s = self.stats
        return (
            f"ToolResultCache(size={s['size']}/{s['max_size']}, "
            f"hits={s['hits']}, misses={s['misses']}, "
            f"hit_rate={s['hit_rate']:.0%})"
        )
