"""
GPT-First 兼容层
=================
向后兼容的薄封装，委托到新的 Advisor + Orchestrator 架构。

所有旧 API 保持不变，消费者无需修改。
内部委托到 GPTFirstOrchestrator + CdpAdvisor。
"""

from __future__ import annotations

import sys
import threading
import time

# ── 懒加载单例 ──────────────────────────────────

_orchestrator = None
_lock = threading.Lock()


def _get_orchestrator():
    """懒加载 GPTFirstOrchestrator 单例。"""
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator

    with _lock:
        if _orchestrator is not None:
            return _orchestrator

        from advisor.cache import AdvisorCache
        from advisor.cdp_advisor import CdpAdvisor
        from advisor.circuit_breaker import CircuitBreaker
        from core.orchestrator import GPTFirstOrchestrator

        advisor = CdpAdvisor(timeout_seconds=6.0)

        # DeepSeek 调用函数 — 在兼容层留空，消费者自行处理融合
        def _dummy_deepseek(prompt: str) -> str:
            return "[CRUX] DeepSeek 不可用（兼容层占位）"

        _orchestrator = GPTFirstOrchestrator(
            advisor=advisor,
            ask_deepseek=_dummy_deepseek,
            cache=AdvisorCache(ttl_seconds=600),
            breaker=CircuitBreaker(
                failure_threshold=3,
                cooldown_seconds=120,
            ),
            timeout_seconds=6.0,
        )

        return _orchestrator


# ── 内部通知 ─────────────────────────────────────

_status_callback = None


def set_status_callback(cb):
    """注入状态通知回调。TUI 启动时调用，将消息路由到 StatusBar。"""
    global _status_callback
    _status_callback = cb
    orch = _get_orchestrator()
    orch.set_status_callback(cb)


def _notify(msg: str):
    """输出状态通知：有回调走回调，否则走 stderr。
    
    这是公开 API — core/cli_handlers.py 直接导入此函数。
    """
    if _status_callback is not None:
        _status_callback(msg)
    else:
        print(f"[gpt_first] {msg}", file=sys.stderr, flush=True)


# ── 全局状态（向后兼容）─────────────────────────

GPT_FIRST_ENABLED = False          # 主开关
GPT_CONNECTED = False              # 启动时连接验证结果
_LAST_PING = 0.0                   # 上次心跳时间戳

# ── 开关控制 ─────────────────────────────────────

def set_gpt_first(enabled: bool):
    """运行时开关 GPT-first 模式"""
    global GPT_FIRST_ENABLED
    GPT_FIRST_ENABLED = enabled
    orch = _get_orchestrator()
    orch.enabled = enabled
    if enabled:
        _notify("GPT-first 模式: ON — 每次查询先问 ChatGPT")
    else:
        _notify("GPT-first 模式: OFF — 直接 DeepSeek 回答")


def is_gpt_first() -> bool:
    return GPT_FIRST_ENABLED


def is_connected() -> bool:
    orch = _get_orchestrator()
    return orch.connected


# ── 启动自检 ─────────────────────────────────────

def bootstrap(background: bool = False) -> bool:
    """
    CRUX 启动时调用：验证 ChatGPT 页面 CDP 连接可用。

    参数:
        background: 为 True 时在新线程中执行，不阻塞启动
    """
    global GPT_CONNECTED
    if not GPT_FIRST_ENABLED:
        return False

    if background:
        t = threading.Thread(
            target=_bootstrap_worker,
            daemon=True,
            name="gpt-first-bootstrap",
        )
        t.start()
        _notify("ChatGPT 连接检测中...（后台进行，不阻塞启动）")
        return True

    return _bootstrap_worker()


def _bootstrap_worker() -> bool:
    """后台工作线程：启动 Advisor 连接"""
    global GPT_CONNECTED
    orch = _get_orchestrator()
    try:
        ok = orch.startup(background=False)
        GPT_CONNECTED = ok
        return ok
    except Exception:
        GPT_CONNECTED = False
        return False


def heartbeat() -> bool:
    """
    心跳检测：每 5 分钟自动 ping 一次保持连接。
    """
    global _LAST_PING, GPT_CONNECTED
    now = time.time()
    if now - _LAST_PING < 300:
        return GPT_CONNECTED

    _LAST_PING = now
    if not GPT_FIRST_ENABLED:
        return False
    orch = _get_orchestrator()
    GPT_CONNECTED = orch.connected
    return GPT_CONNECTED


# ── 核心路由 ─────────────────────────────────────

def route_via_gpt(user_query: str, timeout: int = 60) -> str | None:
    """
    将用户查询发送到 ChatGPT（CDP 浏览器）并返回回复。
    
    参数:
        user_query: 用户输入
        timeout: 单次超时秒数（保留参数，实际由 advisor 控制）
    
    返回:
        GPT 回复文本，或 None（失败/超时/已关闭）
    """
    if not GPT_FIRST_ENABLED:
        return None

    orch = _get_orchestrator()
    if not orch.connected:
        return None

    try:
        result = orch.ask_advisor_direct(user_query)
        if result.ok:
            return result.content
        return None
    except Exception:
        return None


def route_with_files(
    text: str, file_paths: list[str], timeout: int = 90
) -> str | None:
    """
    将用户文本 + 文件附件发送到 ChatGPT 并返回回复。
    支持图片、PDF、代码文件等任意格式。

    参数:
        text: 分析问题/提示
        file_paths: 要上传的文件路径列表
        timeout: 超时秒数（保留参数）

    返回:
        GPT 回复文本，或 None（失败/超时/已关闭）
    """
    if not GPT_FIRST_ENABLED:
        return None

    orch = _get_orchestrator()
    if not orch.connected:
        return None

    try:
        result = orch.analyze_files(file_paths, text)
        if result.ok:
            return result.content
        return None
    except Exception:
        return None


def route_with_image(text: str, image_path: str, timeout: int = 90) -> str | None:
    """向后兼容：发送单张图片到 ChatGPT。等价于 route_with_files(text, [image_path])。"""
    return route_with_files(text, [image_path], timeout)


def wrap_query(user_query: str, fallback_func=None) -> str:
    """
    完整包装：先问 GPT → 有回复就融合 → 没有就走 fallback。
    
    参数:
        user_query: 用户输入
        fallback_func: 降级回调（返回 DeepSeek 回复）
    
    返回:
        最终展示给用户的回复文本
    """
    if not GPT_FIRST_ENABLED:
        if fallback_func:
            return fallback_func()
        return ""

    _notify("咨询 ChatGPT 中...")

    gpt_reply = route_via_gpt(user_query)

    if gpt_reply:
        _notify("ChatGPT 回复已收到")
        fused = (
            "━━━ 🤖 ChatGPT 回复 ━━━\n\n"
            f"{gpt_reply}\n\n"
            "━━━ 🔧 CRUX 补充 ━━━\n"
        )
        if fallback_func:
            supplemented_query = (
                f"用户问题: {user_query}\n"
                f"ChatGPT 的回复: {gpt_reply}\n\n"
                "请基于 ChatGPT 的回复做补充、修正或扩展，不要重复 ChatGPT 已经说过的话。"
            )
            extra = fallback_func(supplemented_query)
            if extra:
                fused += extra
        return fused
    else:
        _notify("GPT 无响应，使用 DeepSeek")
        if fallback_func:
            return fallback_func()
        return ""
