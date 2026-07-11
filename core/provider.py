"""Provider manager with automatic failover + model registry.

This module is the **single source of truth** for:
  - core/chat.py: MODEL_ALIASES, MODEL_INFO, TOOL_CALLING_MODELS, MODEL_PROVIDER_MAP
  - core/config.py: MODELS
  - models.json: runtime config
  - crux_studio.py: _chat_repl() model switching

Adding a new provider/model now requires changes in ONE place (MODEL_REGISTRY + models.json).

Health tracking: records recent response latencies per provider to detect
chronically slow providers and surface warnings (no auto-switch).
"""

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.provider")

ROOT = Path(__file__).resolve().parent.parent


__all__ = [
    "ROOT",
    "ModelInfo",
    "NoProviderAvailable",
    "ProviderManager",
    "ProviderState",
    "get_capability_info",
    "get_context_window",
    "get_max_tokens_for_model",
    "get_model_description",
    "get_model_info",
    "get_provider_manager",
    "get_provider_name",
    "get_thinking_params_for_model",
    "get_tool_calling_models",
    "get_vision_models",
    "model_supports_tools",
    "model_supports_vision",
    "register_model",
    "resolve_model_alias",
]


# ═══════════════════════════════════════════════════════════════════
# Model Registry — 单一真源：模型 ID → 能力/别名/供应商映射
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ModelInfo:
    """模型元信息 — 模型路由唯一真源。"""

    id: str  # 模型 ID（发送给 API 的值）
    name: str  # 人类可读名称
    provider_id: str  # 所属供应商 ID（对应 models.json 的 key）
    provider_name: str  # 供应商人类可读名（注入系统提示词）
    description: str = ""  # 能力简述（/help 和 /model 切换时展示）
    supports_tools: bool = False  # 是否支持 OpenAI tool calling
    supports_thinking: bool = False  # 是否支持深度思考
    supports_vision: bool = False  # 是否支持多模态图片理解
    tier: str = "pro"  # light / pro / heavy（用于 models.json 的 models 字段）
    aliases: tuple[str, ...] = ()  # 用户可用的快捷别名（如 "light", "pro"）
    model_type: str = "text"  # "text" | "image" | "video" — 用于 validate_model 类型校验
    context_window: int = 128000  # 总上下文窗口（tokens）
    max_output_tokens: int = 8192  # API 最大输出 tokens
    cost_level: int = 1  # 0=free, 1=cheap, 2=normal, 3=expensive
    best_for: tuple[str, ...] = ()  # 最适合的任务类型
    # 定价（美元）：text 模型 input_per_1k/output_per_1k；image/video per_call
    pricing: dict[str, float] | None = None

    @property
    def model_id(self) -> str:
        """向后兼容别名 — 等效于 id。"""
        return self.id


# 全局模型注册表 — 新增模型只需在这里加一条
MODEL_REGISTRY: dict[str, ModelInfo] = {}


def _register_defaults():
    """注册内置模型。启动时自动调用一次。"""
    global MODEL_REGISTRY

    models = [
        # ── 智谱免费模型（视觉优先，理解能力优于 agnes）──
        ModelInfo(
            id="GLM-4V-Flash",
            name="GLM-4V-Flash (智谱视觉)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱最新免费视觉理解，OCR/描述/场景识别（新版，替代 glm-4.6v）",
            supports_vision=True,
            tier="light",
            aliases=("glm-4v", "glm-v", "zhipu-vision"),
            context_window=32768,
            max_output_tokens=1024,
            cost_level=0,
            pricing={"input_per_1k": 0.0, "output_per_1k": 0.0},
        ),
        # ── CRUX AI models ──
        ModelInfo(
            id="agnes-2.0-flash",
            name="CRUX 2.0 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="视觉理解 + tool calling + 深度推理",
            supports_tools=True,
            supports_thinking=False,
            supports_vision=True,
            tier="pro",
            aliases=("agnes", "agnes-pro"),
            context_window=128000,
            max_output_tokens=16384,
            cost_level=1,
            pricing={"input_per_1k": 0.003, "output_per_1k": 0.012},
        ),
        # ── CRUX 图片生成 ──
        ModelInfo(
            id="agnes-image-2.1-flash",
            name="CRUX Image 2.1 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="高精度文生图/图生图，支持多图参考",
            tier="pro",
            model_type="image",
            aliases=("img-hd", "img-edit", "agnes-image"),
            context_window=0,
            max_output_tokens=0,
            cost_level=2,
            pricing={"per_call": 0.03},
        ),
        ModelInfo(
            id="agnes-image-2.0-flash",
            name="CRUX Image 2.0 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="图片编辑/变体，支持多图+标签控制",
            tier="pro",
            model_type="image",
            aliases=("img-edit-v2",),
            context_window=0,
            max_output_tokens=0,
            cost_level=2,
            pricing={"per_call": 0.02},
        ),
        # ── CRUX 视频生成 ──
        ModelInfo(
            id="agnes-video-v2.0",
            name="CRUX Video V2.0",
            provider_id="crux",
            provider_name="CRUX AI",
            description="文生视频/图生视频/关键帧动画",
            tier="pro",
            model_type="video",
            aliases=("video", "vid"),
            context_window=0,
            max_output_tokens=0,
            cost_level=3,
            pricing={"per_call": 0.35},
        ),
        # ── DeepSeek — 主要编码模型 ──
        ModelInfo(
            id="deepseek-v4-pro",
            name="DeepSeek V4 Pro",
            provider_id="deepseek",
            provider_name="DeepSeek V4 Pro (1M 上下文)",
            description="百万上下文，代码/推理，视觉走独立通道",
            supports_tools=True,
            supports_thinking=True,
            tier="heavy",
            aliases=("deepseek", "ds", "dsv4pro", "pro", "reasoner"),
            context_window=1000000,
            max_output_tokens=384000,
            cost_level=2,
            pricing={"input_per_1k": 0.002, "output_per_1k": 0.008},
        ),
        ModelInfo(
            id="deepseek-v4-flash",
            name="DeepSeek V4 Flash",
            provider_id="deepseek",
            provider_name="DeepSeek V4 Flash (1M 上下文)",
            description="轻量快档，日常对话/简单任务，1M 上下文，免费",
            supports_tools=True,
            supports_thinking=True,
            tier="light",
            aliases=("flash", "dsflash", "dsv4flash", "light"),
            context_window=1000000,
            max_output_tokens=384000,
            cost_level=1,
            pricing={"input_per_1k": 0.001, "output_per_1k": 0.004},
        ),
        # ── Local (llama.cpp server) ──
        # model id "local-model" is a placeholder — llama-server accepts any model id
        # and serves whatever model was loaded with -m flag.
        ModelInfo(
            id="local-model",
            name="Local Model (llama.cpp)",
            provider_id="local",
            provider_name="Local (llama.cpp)",
            description="Qwen3.6-35B-A3B MoE (IQ4_NL) — 35B total / 3B active, uncensored",
            supports_tools=True,
            supports_thinking=True,
            tier="pro",
            aliases=("local", "llama", "qwen", "qwen3"),
            context_window=32768,
            max_output_tokens=8192,
            cost_level=0,
            pricing={"input_per_1k": 0.0, "output_per_1k": 0.0},
        ),
    ]
    for m in models:
        MODEL_REGISTRY[m.id] = m


_register_defaults()


# ── 查询接口 ──────────────────────────────────────────────


def get_model_info(model_id: str) -> ModelInfo | None:
    """根据模型 ID 查元信息，找不到返回 None。"""
    return MODEL_REGISTRY.get(model_id)


def resolve_model_alias(name: str | None) -> str | None:
    """将用户输入的别名（light/pro/deepseek/zhipu 等）解析为模型 ID。

    优先查 MODEL_REGISTRY 的别名，再直接查 ID 匹配，最后查 models.json。
    """
    if not name or not isinstance(name, str):
        return None
    # 1. 别名匹配（无歧义：同一别名只注册一次）
    name_lower = name.lower().strip()
    for m in MODEL_REGISTRY.values():
        if name_lower in m.aliases:
            return m.id

    # 2. 直接 ID 匹配
    if name in MODEL_REGISTRY:
        return name

    # 3. 大小写不敏感 ID 匹配
    for mid in MODEL_REGISTRY:
        if mid.lower() == name_lower:
            return mid

    # 4. models.json 中的 provider 级别名（向后兼容）
    mgr = get_provider_manager()
    for _pid, p in mgr.providers.items():
        p_aliases = p.get("model_aliases", {})
        if name in p_aliases:
            return p_aliases[name]
        for _tier, mid in p.get("models", {}).items():
            if mid == name:
                return mid

    return None


def get_tool_calling_models() -> set[str]:
    """返回所有支持 tool calling 的模型 ID 集合。"""
    return {m.id for m in MODEL_REGISTRY.values() if m.supports_tools}


def get_model_description(model_id: str) -> str:
    """返回模型的能力描述字符串（用于 /help 和 /model 展示）。"""
    m = MODEL_REGISTRY.get(model_id)
    if m:
        return f"{m.name}（{m.description}）"
    return model_id


def get_provider_name(model_id: str) -> str:
    """返回模型所属供应商的人类可读名（注入系统提示词用）。"""
    m = MODEL_REGISTRY.get(model_id)
    if m:
        return m.provider_name
    return model_id


def register_model(info: ModelInfo) -> None:
    """动态注册一个模型到全局注册表。"""
    MODEL_REGISTRY[info.id] = info


def model_supports_tools(model_id: str) -> bool:
    """判断指定模型是否支持 tool calling。"""
    return model_id in get_tool_calling_models()


def get_vision_models() -> list[str]:
    """返回所有支持多模态视觉理解的模型 ID 列表。

    视觉通道 fallback 链：CRUX 主力（最优）→ 智谱兜底（免费）。
    """
    return [m.id for m in MODEL_REGISTRY.values() if m.supports_vision]


def model_supports_vision(model_id: str) -> bool:
    """判断指定模型是否支持多模态图片理解。"""
    return model_id in get_vision_models()


def get_capability_info(model_id: str) -> ModelInfo | None:
    """根据 model_id 或别名查询 ModelInfo，找不到返回 None。"""
    resolved = resolve_model_alias(model_id)
    if resolved:
        return MODEL_REGISTRY.get(resolved)
    return MODEL_REGISTRY.get(model_id)


def get_context_window(model_id: str) -> int:
    """返回模型的总上下文窗口（tokens），未知模型返回 128000。"""
    info = get_capability_info(model_id)
    return info.context_window if info else 128000


def get_max_tokens_for_model(model_id: str, is_tool_call: bool = False) -> int:
    """返回模型的最大输出 tokens，tool call 场景自动封顶 8192。

    非 tool-call 场景：优先用 ProviderAdapter.default_max_tokens（供应商推荐值），
    未知模型回退到 16384。

    未知模型：返回 16384（默认）或 8192（tool call）。
    """
    info = get_capability_info(model_id)
    if info is None:
        return max(256, 8192 if is_tool_call else 16384)
    if is_tool_call:
        return max(256, min(info.max_output_tokens, 8192))
    # 非 tool-call: 使用 ProviderAdapter 的推荐值（比 ModelInfo.max_output_tokens 更保守）
    try:
        from core.provider_adapter import get_adapter
        adapter = get_adapter(info.provider_id)
        if adapter and adapter.default_max_tokens:
            return max(256, adapter.default_max_tokens)
    except ImportError:
        pass
    return max(256, min(info.max_output_tokens, 16384))


def get_thinking_params_for_model(model_id: str) -> dict[str, Any]:
    """返回模型的思考参数 dict，不支持思考则返回 {}。

    需要 ProviderAdapter.build_thinking_params() 处理供应商差异。
    """
    info = get_capability_info(model_id)
    if info is None or not info.supports_thinking:
        return {}
    # 委托 ProviderAdapter 处理供应商特定参数格式
    from core.provider_adapter import get_adapter as _get_adapter

    adapter = _get_adapter(info.provider_id)
    return adapter.build_thinking_params()


# ═══════════════════════════════════════════════════════════════════
# Provider State — 健康追踪 + 冷却
# ═══════════════════════════════════════════════════════════════════


class ProviderState:
    """Tracks which provider is active and which have failed.

    Implements circuit breaker pattern:
    - CLOSED: normal operation
    - OPEN: >=3 consecutive failures, skip for cooldown_sec
    - HALF_OPEN: after cooldown, allow 1 probe request
    """

    CIRCUIT_CLOSED = "CLOSED"
    CIRCUIT_OPEN = "OPEN"
    CIRCUIT_HALF_OPEN = "HALF_OPEN"

    def __init__(self, active: str, cooldown_sec: float = 30.0) -> None:
        self.active = active
        self.cooldown_sec = cooldown_sec
        self._down_since: dict[str, float] = {}  # provider_id -> timestamp
        self._switch_count: int = 0
        # ── 健康追踪：最近 N 次响应延迟（秒）──
        self._latencies: dict[str, deque] = {}  # provider_id -> deque of float
        self._max_latency_samples = 10
        # ── 熔断保护：连续失败计数 + 状态 ──
        self._circuit: dict[str, dict] = {}  # provider_id -> {state, failures, opened_at, probe_count}

    # ── 熔断保护方法 ────────────────────────────────────

    def _get_circuit(self, pid: str) -> dict:
        if pid not in self._circuit:
            self._circuit[pid] = {
                "state": self.CIRCUIT_CLOSED,
                "consecutive_failures": 0,
                "last_failure_at": 0.0,
                "opened_at": 0.0,
                "probe_count": 0,
            }
        return self._circuit[pid]

    def record_failure(self, pid: str) -> None:
        """记录一次失败，达到阈值时打开熔断器。"""
        c = self._get_circuit(pid)
        c["consecutive_failures"] += 1
        c["last_failure_at"] = time.time()
        if c["consecutive_failures"] >= 3:
            c["state"] = self.CIRCUIT_OPEN
            c["opened_at"] = time.time()
            c["probe_count"] = 0

    def record_success(self, pid: str) -> None:
        """记录一次成功，关闭熔断器。"""
        c = self._get_circuit(pid)
        c["state"] = self.CIRCUIT_CLOSED
        c["consecutive_failures"] = 0
        c["probe_count"] = 0

    def circuit_can_try(self, pid: str) -> bool:
        """熔断感知：此 provider 当前是否允许调用。"""
        c = self._get_circuit(pid)
        if c["state"] == self.CIRCUIT_CLOSED:
            return True
        if c["state"] == self.CIRCUIT_OPEN:
            elapsed = time.time() - c["opened_at"]
            if elapsed >= self.cooldown_sec:
                c["state"] = self.CIRCUIT_HALF_OPEN
                # probe_count=1 表示"此次探测名额已分配"，避免多放一次
                c["probe_count"] = 1
                return True
            return False
        # HALF_OPEN: 只允许一次探测
        if c["probe_count"] >= 1:
            return False
        c["probe_count"] += 1
        return True

    def circuit_state(self, pid: str) -> str:
        """返回 provider 的熔断状态（CLOSED / OPEN / HALF_OPEN）。"""
        return self._get_circuit(pid)["state"]

    # ── 原健康追踪方法 ──────────────────────────────────

    def record_latency(self, provider_id: str, elapsed_sec: float):
        """Record a response latency sample for the given provider."""
        if provider_id not in self._latencies:
            self._latencies[provider_id] = deque(maxlen=self._max_latency_samples)
        self._latencies[provider_id].append(elapsed_sec)

    def health_hint(self) -> str | None:
        """Check active provider health, return warning string or None."""
        samples = self._latencies.get(self.active)
        if not samples or len(samples) < 3:
            return None
        avg = sum(samples) / len(samples)
        if avg > 15.0:
            return (
                f"⚠️ 当前供应商 '{self.active}' 平均响应 {avg:.1f}s，"
                f"可能较慢。可用: {', '.join(self._latencies.keys())}。"
                f"如需切换: /provider"
            )
        return None

    def mark_down(self, provider_id: str):
        """Mark a provider as temporarily down."""
        self._down_since[provider_id] = time.time()

    def is_down(self, provider_id: str) -> bool:
        """Check if provider is in cooldown."""
        since = self._down_since.get(provider_id, 0)
        return (time.time() - since) < self.cooldown_sec

    def available(self, provider_ids: list[str]) -> list[str]:
        """Return providers that are not in cooldown, active first."""
        ordered = [self.active] + [p for p in provider_ids if p != self.active]
        return [p for p in ordered if not self.is_down(p) and self.circuit_can_try(p)]

    def available_by_latency(self, provider_ids: list[str]) -> list[str]:
        """Return available providers sorted by average latency (fastest first)."""
        available_list = self.available(provider_ids)
        if len(available_list) <= 1:
            return available_list

        def avg_latency(pid: str) -> float:
            samples = self._latencies.get(pid, deque())
            if not samples:
                return 999.0
            avg = sum(samples) / len(samples)
            if pid == self.active:
                avg *= 0.8
            return avg

        return sorted(available_list, key=avg_latency)


# ═══════════════════════════════════════════════════════════════════
# Provider Manager — 多供应商管理 + 自动 failover
# ═══════════════════════════════════════════════════════════════════


class ProviderManager:
    """Manages multiple LLM providers with automatic failover.

    Usage:
        mgr = ProviderManager()
        mgr.load()

        try:
            client = mgr.create_client()  # auto-selects best provider
        except NoProviderAvailable:
            print("All providers are down")
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (ROOT / "models.json")
        self.providers: dict = {}
        self.fallback_priority: list[str] = []
        self.state = ProviderState(active="crux")

    def load(self):
        """Load provider configuration from models.json."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("models.json corrupted (%s), using defaults", e)
            return

        self.providers = cfg.get("providers", {})
        fallback_cfg = cfg.get("fallback", {})
        self.fallback_priority = fallback_cfg.get("priority", [])
        active = cfg.get("active", "deepseek")
        # ── 校验: 活跃供应商必须有文本模型 ──
        if active in self.providers:
            pmodels = self.providers[active].get("models", {})
            if not pmodels.get("pro") and not pmodels.get("light"):
                logger.info("Active provider '%s' has no text models, auto-correcting to deepseek", active)
                active = "deepseek"
                # 自动修正 models.json，下次不再报警
                try:
                    cfg["active"] = active
                    with open(self.config_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                except (OSError, json.JSONDecodeError):
                    pass
        self.state.active = active

    def save_active(self) -> str:
        """Persist current active provider to models.json."""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["active"] = self.state.active
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            return self.state.active
        except (OSError, json.JSONDecodeError):
            return self.state.active

    def set_active(self, provider_id: str):
        """Manually switch active provider. Refuses providers without text models."""
        if provider_id not in self.providers:
            return
        pmodels = self.providers[provider_id].get("models", {})
        if not pmodels.get("pro") and not pmodels.get("light"):
            logger.warning("Cannot activate '%s': no text models (media-only provider)", provider_id)
            return
        self.state.active = provider_id

    def ping(self) -> bool:
        """Quick health check: probe active provider's /models endpoint. Returns True if alive."""
        try:
            import urllib.request

            provider = self.providers.get(self.state.active, {})
            base = provider.get("base_url", "")
            if not base:
                return False
            api_key = provider.get("api_key") or os.getenv(f"{self.state.active.upper()}_API_KEY", "")
            req = urllib.request.Request(
                f"{base.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except (OSError, RuntimeError, ValueError) as e:
            # ping 是 watchdog/circuit-breaker 的决策依据，记录失败原因便于排查
            # （网络错误 vs API key 错误 vs DNS 失效在此可区分）
            logger.debug("provider.ping(%s) failed: %s: %s", self.state.active, type(e).__name__, e)
            return False

    @property
    def active_provider(self) -> str:
        return self.state.active

    def fallback(self, request: dict | None = None) -> bool:
        """Switch to next available provider, scored by policy. Returns True on success.

        When provider_policy is available, providers are ordered by score_provider()
        (task_type, circuit state, budget, history). Falls back to simple ordering
        if the policy module is unavailable.
        """
        available = self.state.available(list(self.providers.keys()))
        if not available:
            return False
        # Policy-scored ordering (smarter than static fallback_priority)
        try:
            from core.provider_policy import select_candidates

            circuit_states = {p: self.state.circuit_state(p) for p in available}
            ordered = select_candidates(request or {"task_type": "text"}, available, circuit_states)
        except ImportError:
            ordered = available
        for pid in ordered:
            if pid == self.state.active:
                continue
            try:
                self.create_client(pid)
                self.state.active = pid
                self.save_active()
                return True
            except NoProviderAvailable:
                continue
        return False

    def create_client(self, provider_id: str | None = None, _depth: int = 0, root_trace_id: str = ""):
        """Create an CruxClient for the given or active provider."""
        if _depth >= 3:
            raise NoProviderAvailable("Provider fallback chain exceeded max depth")
        if not root_trace_id:
            try:
                from core.multi_agent import get_current_root_trace_id

                root_trace_id = get_current_root_trace_id()
            except ImportError:
                pass
        from core.client import CruxClient

        pid = provider_id or self.state.active
        if pid not in self.providers:
            pid = self._first_available()
            if not pid:
                raise NoProviderAvailable("No provider configured")

        provider = self.providers[pid]
        api_key = provider.get("api_key") or os.getenv(f"{pid.upper()}_API_KEY", "")
        # Legacy fallback: CRUX provider also accepts AGNES_API_KEY (pre-rename)
        if not api_key and pid == "crux":
            api_key = os.getenv("AGNES_API_KEY", "")
        # Ensure ASCII-only (httpx rejects non-ASCII headers)
        # P2-fix: errors="strict" — 拒绝非ASCII字符（如中文引号/BOM），
        # 避免 Key 被静默截断导致认证失败而不报错。
        try:
            api_key = api_key.encode("ascii", errors="strict").decode("ascii") if api_key else ""
        except UnicodeEncodeError:
            logger.exception(
                "API key for provider '%s' contains non-ASCII characters. "
                "Check your .env / models.json for stray full-width chars or BOM.",
                pid,
            )
            api_key = ""
        # Non-authenticated providers may bypass auth checks.
        # auth_required=false → use a placeholder key instead of falling back to
        # another provider (which would cause session.model vs client.base_url mismatch).
        if not api_key and provider.get("auth_required", True):
            fallback = self._first_available(exclude={pid})
            if fallback:
                import logging

                try:
                    from core.provider_history import record_call

                    record_call(pid, "", False, 0, "fallback to " + fallback)
                except ImportError:
                    pass
                logging.getLogger("crux").info(
                    "provider fallback: %s -> %s (depth=%d, trace=%s)", pid, fallback, _depth + 1, root_trace_id
                )
                return self.create_client(fallback, _depth=_depth + 1, root_trace_id=root_trace_id)
            raise NoProviderAvailable(f"No API key for provider '{pid}'")

        return CruxClient(api_key=api_key, base_url=provider["base_url"])

    def handle_failure(
        self, failed_provider: str, status_code: int, _depth: int = 0
    ) -> tuple[object | None, str | None]:
        """Called when a provider request fails. Returns (new_client, new_provider_id)
        if failover succeeded, or (None, None) if all providers exhausted.

        Implements failover depth protection: max 3 cascading failovers.
        """
        if _depth >= 3:
            logger.warning("failover chain exceeded max depth (3), giving up")
            return None, None

        # 熔断保护：记录失败，检查是否还有 provider 可用
        self.state.record_failure(failed_provider)

        available = self.state.available(list(self.providers.keys()))
        for pid in available:
            if pid == failed_provider:
                continue
            try:
                client = self.create_client(pid)
                self.state.active = pid
                # 不永久保存——failover 是临时的，下次启动仍用用户首选
                return client, pid
            except NoProviderAvailable:
                continue

        return None, None

    def _first_available(self, exclude: set | None = None) -> str | None:
        """Find the first provider with a valid API key."""
        exclude = exclude or set()
        for pid in self.providers:
            if pid in exclude:
                continue
            if self.state.is_down(pid):
                continue
            p = self.providers[pid]
            key = p.get("api_key") or os.getenv(f"{pid.upper()}_API_KEY", "")
            # Legacy fallback: CRUX provider also accepts AGNES_API_KEY
            if not key and pid == "crux":
                key = os.getenv("AGNES_API_KEY", "")
            if key:
                return pid
        return None

    def get_active_models(self) -> dict[str, str]:
        """Get all tier→model-id mappings for the active provider."""
        provider = self.providers.get(self.state.active, {})
        return dict(provider.get("models", {}))

    def get_model(self, tier: str = "pro") -> str:
        """Get the model ID for the active provider."""
        provider = self.providers.get(self.state.active, {})
        return provider.get("models", {}).get(tier, "unknown")


class NoProviderAvailable(Exception):
    """Raised when all providers are exhausted or lack API keys."""

    pass


# Singleton
_mgr: ProviderManager | None = None
_mgr_lock = threading.Lock()


def get_provider_manager() -> ProviderManager:
    global _mgr
    if _mgr is None:
        with _mgr_lock:
            if _mgr is None:
                _mgr = ProviderManager()
                _mgr.load()
    return _mgr


def reset_provider_manager() -> None:
    """Reset the provider singleton (test isolation / hot reload).

    ProviderManager holds only in-memory latency/cooldown state, no threads
    or OS resources. Note: MODEL_REGISTRY is repopulated at import time and
    is intentionally left intact (it reflects the shipped models.json).
    """
    global _mgr
    _mgr = None
