"""
GPT-First 主编排器
===================
协调 Advisor 层和 DeepSeek 主脑的交互流程。

流程:
1. 缓存命中 → 直接返回
2. 熔断器开启 → 跳过 GPT
3. 调用 Advisor.ask() → 获取顾问建议
4. 构建融合 prompt → 交给 DeepSeek
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from advisor.base import AdvisorClient, AdvisorResult
from advisor.cache import AdvisorCache
from advisor.circuit_breaker import CircuitBreaker


@dataclass(frozen=True)
class CRUXResponse:
    """CRUX 完整回复，包含 Advisor 元数据。"""

    content: str
    advisor_used: bool
    advisor_status: str
    advisor_source: str
    advisor_latency_ms: int
    advisor_error: str | None = None


class GPTFirstOrchestrator:
    """GPT-first 主编排器。

    管理 Advisor 生命周期、缓存、熔断，将 GPT 顾问结果融合进 CRUX 主流程。
    线程安全。
    """

    def __init__(
        self,
        advisor: AdvisorClient,
        ask_deepseek: Callable[[str], str],
        cache: AdvisorCache | None = None,
        breaker: CircuitBreaker | None = None,
        timeout_seconds: float = 6.0,
    ) -> None:
        self.advisor = advisor
        self._ask_deepseek = ask_deepseek  # DeepSeek 调用函数
        self.cache = cache or AdvisorCache(ttl_seconds=600)
        self.breaker = breaker or CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=120,
        )
        self.timeout_seconds = timeout_seconds
        self._enabled = False
        self._lock = threading.Lock()
        self._status_callback: Callable[[str], None] | None = None

    # ── 生命周期 ──────────────────────────────────

    def startup(self, background: bool = False) -> bool:
        """初始化 Advisor 连接。

        Args:
            background: True 时在新线程中执行，不阻塞调用方。

        Returns:
            True 如果启动成功（或已启动后台任务）。
        """
        if background:
            t = threading.Thread(
                target=self._startup_worker,
                daemon=True,
                name="gpt-first-startup",
            )
            t.start()
            self._notify("ChatGPT 连接检测中...（后台进行）")
            return True
        return self._startup_worker()

    def _startup_worker(self) -> bool:
        try:
            self.advisor.startup()
            self.breaker.record_success()
            self._notify("ChatGPT 已就绪 ✅")
            return True
        except Exception as e:
            self.breaker.record_failure()
            self._notify(f"ChatGPT 连接失败: {e}")
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def connected(self) -> bool:
        """GPT Advisor 当前是否可用。"""
        return self._enabled and self.advisor.health()

    def set_status_callback(self, cb: Callable[[str], None]) -> None:
        """注入状态通知回调（TUI StatusBar）。"""
        self._status_callback = cb

    # ── 核心查询 ──────────────────────────────────

    def consult(self, user_query: str, crux_context: str = "") -> AdvisorResult:
        """咨询 GPT Advisor（带缓存和熔断）。

        Returns:
            AdvisorResult，ok=False 时调用方应走降级。
        """
        if not self._enabled:
            return AdvisorResult(
                status="unavailable",
                source="orchestrator",
                error="GPT-first 未开启",
            )

        # 缓存检查
        cached = self.cache.get(user_query, crux_context)
        if cached is not None:
            return cached

        # 熔断检查
        if not self.breaker.allow():
            return AdvisorResult(
                status="unavailable",
                source="circuit_breaker",
                error=f"GPT advisor 熔断中，剩余 {self.breaker.snapshot()['remaining_cooldown']:.0f}s",
            )

        # 调用 Advisor
        self._notify("咨询 ChatGPT 中...")
        started = time.perf_counter()

        try:
            result = self.advisor.ask(user_query, crux_context)
        except Exception as e:
            result = AdvisorResult(
                status="error",
                source="cdp_chatgpt",
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(e),
            )

        if result.ok:
            self.breaker.record_success()
            self.cache.set(user_query, crux_context, result)
            self._notify("ChatGPT 回复已收到")
        else:
            self.breaker.record_failure()
            self._notify(f"GPT 无响应 ({result.status})，使用 DeepSeek")

        return result

    def answer(self, user_query: str, crux_context: str = "") -> CRUXResponse:
        """完整流程：咨询 GPT → 融合 → DeepSeek 回答。

        Returns:
            CRUXResponse，包含最终回答和 Advisor 元数据。
        """
        from core.fusion import build_fusion_prompt

        advisor_result = self.consult(user_query, crux_context)

        fusion_prompt = build_fusion_prompt(
            user_query=user_query,
            crux_context=crux_context,
            advisor_result=advisor_result,
        )

        final_answer = self._ask_deepseek(fusion_prompt)

        return CRUXResponse(
            content=final_answer,
            advisor_used=advisor_result.ok,
            advisor_status=advisor_result.status,
            advisor_source=advisor_result.source,
            advisor_latency_ms=advisor_result.latency_ms,
            advisor_error=advisor_result.error,
        )

    def ask_advisor_direct(self, query: str, context: str = "") -> AdvisorResult:
        """直接咨询 GPT，不做 DeepSeek 融合。用于简单问答。"""
        return self.consult(query, context)

    # ── 图片分析 ──────────────────────────────────

    def analyze_files(
        self, file_paths: list[str], prompt: str = ""
    ) -> AdvisorResult:
        """让 GPT 分析文件附件（图片、PDF、代码等任意格式）。

        Args:
            file_paths: 要上传的文件路径列表
            prompt: 分析提示（可选）

        Returns:
            AdvisorResult
        """
        if not self._enabled:
            return AdvisorResult(
                status="unavailable",
                source="orchestrator",
                error="GPT-first 未开启",
            )
        if not self.breaker.allow():
            return AdvisorResult(
                status="unavailable",
                source="circuit_breaker",
                error="GPT advisor 熔断中",
            )

        query = prompt or "请分析这些文件的内容，描述关键信息。"
        return self.advisor.ask_with_files(query, file_paths, "")

    def analyze_image(
        self, image_path: str, prompt: str = ""
    ) -> AdvisorResult:
        """向后兼容：让 GPT 分析单张图片。等价于 analyze_files([image_path], prompt)。"""
        return self.analyze_files([image_path], prompt)

    # ── 诊断 ──────────────────────────────────────

    def snapshot(self) -> dict:
        """返回当前状态快照。"""
        return {
            "enabled": self._enabled,
            "connected": self.connected,
            "breaker": self.breaker.snapshot(),
            "cache_size": self.cache.size,
        }

    # ── 内部 ──────────────────────────────────────

    def _notify(self, msg: str) -> None:
        """发送状态通知。"""
        if self._status_callback is not None:
            self._status_callback(msg)
        else:
            import sys
            print(f"[gpt_first] {msg}", file=sys.stderr, flush=True)
