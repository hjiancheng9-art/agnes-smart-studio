"""Provider manager with automatic failover + model registry.

This module is the **single source of truth** for:
  - core/chat.py: MODEL_ALIASES, MODEL_INFO, TOOL_CALLING_MODELS, MODEL_PROVIDER_MAP
  - core/config.py: MODELS
  - models.json: runtime config
  - ui/cli.py: _load_models_config / _chat_switch_model

Adding a new provider/model now requires changes in ONE place (MODEL_REGISTRY + models.json).

Health tracking: records recent response latencies per provider to detect
chronically slow providers and surface warnings (no auto-switch).
"""

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("crux.provider")

ROOT = Path(__file__).resolve().parent.parent


__all__ = [
    "ModelInfo",
    "NoProviderAvailable",
    "ProviderManager",
    "ProviderState",
    "ROOT",
    "get_model_description",
    "get_model_info",
    "get_provider_manager",
    "get_provider_name",
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
    """模型元信息。"""

    id: str  # 模型 ID（发送给 API 的值）
    name: str  # 人类可读名称
    provider_id: str  # 所属供应商 ID（对应 models.json 的 key）
    provider_name: str  # 供应商人类可读名（注入系统提示词）
    description: str = ""  # 能力简述（/help 和 /model 切换时展示）
    supports_tools: bool = False  # 是否支持 OpenAI tool calling
    supports_thinking: bool = False  # 是否支持深度思考
    supports_vision: bool = False  # 是否支持多模态图片理解
    tier: str = "pro"  # light / pro（用于 models.json 的 models 字段）
    aliases: tuple[str, ...] = ()  # 用户可用的快捷别名（如 "light", "pro"）
    model_type: str = "text"  # "text" | "image" | "video" — 用于 validate_model 类型校验


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
        ),
        ModelInfo(
            id="glm-4.1v-thinking-flash",
            name="GLM-4.1V-Thinking-Flash (智谱)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱视觉+深度推理，支持thinking参数，复杂图表/代码/计数（免费）",
            supports_vision=True,
            supports_thinking=True,
            tier="pro",
            aliases=("glm-vt", "zhipu-think-v"),
        ),
        # ── 智谱免费对话模型 ──
        ModelInfo(
            id="glm-4.7-flash",
            name="GLM-4.7-Flash (智谱免费)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱旗舰免费对话，128K，tool calling，免费",
            supports_tools=True,
            tier="pro",
            aliases=("glm", "zhipu-chat", "glm4"),
        ),
        ModelInfo(
            id="glm-4-flash-250414",
            name="GLM-4-Flash (智谱稳定)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱稳定版，128K，日常任务，免费",
            supports_tools=True,
            tier="light",
            aliases=("glm-stable", "zhipu-light"),
        ),
        ModelInfo(
            id="GLM-Z1-Flash",
            name="GLM-Z1-Flash (智谱推理)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱免费推理模型，数学/代码/逻辑深度思考",
            supports_tools=True,
            supports_thinking=True,
            tier="heavy",
            aliases=("z1", "glm-z1", "zhipu-reasoner"),
        ),
        # ── 智谱免费生图/生视频 ──
        ModelInfo(
            id="CogView-3-Flash",
            name="CogView-3-Flash (智谱生图)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱免费文生图，支持多尺寸",
            tier="light",
            model_type="image",
            aliases=("cogview", "zhipu-img"),
        ),
        ModelInfo(
            id="CogVideoX-Flash",
            name="CogVideoX-Flash (智谱生视频)",
            provider_id="zhipu",
            provider_name="Zhipu GLM",
            description="智谱免费文生视频/图生视频，5秒+",
            tier="light",
            model_type="video",
            aliases=("cogvideo", "zhipu-vid"),
        ),
        # ── CRUX AI models (vision fallback + media generation only, not for coding) ──
        ModelInfo(
            id="agnes-1.5-flash",
            name="CRUX 1.5 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="视觉理解 fallback（智谱超载时启用），不参与编码",
            supports_vision=True,
            tier="light",
            aliases=("light",),
        ),
        ModelInfo(
            id="agnes-2.0-flash",
            name="CRUX 2.0 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="视觉 + 多模态生图/视频，不参与编码",
            supports_tools=True,
            supports_thinking=True,
            supports_vision=True,
            tier="pro",
            aliases=("pro",),
        ),
        ModelInfo(
            id="deepseek-v4-pro",
            name="DeepSeek V4 Pro",
            provider_id="deepseek",
            provider_name="DeepSeek V4 Pro (1M 上下文)",
            description="百万上下文，代码/推理，视觉走独立通道",
            supports_tools=True,
            supports_thinking=True,
            tier="pro",
            aliases=("deepseek", "ds", "dsv4pro"),
        ),
        ModelInfo(
            id="deepseek-v4-flash",
            name="DeepSeek V4 Flash",
            provider_id="deepseek",
            provider_name="DeepSeek V4 Flash (1M 上下文)",
            description="轻量快档，日常对话/简单任务，1M 上下文，免费",
            supports_tools=True,
            tier="light",
            aliases=("flash", "dsflash", "dsv4flash"),
        ),
        ModelInfo(
            id="deepseek-chat",
            name="DeepSeek Chat (V3)",
            provider_id="deepseek",
            provider_name="DeepSeek Chat",
            description="DeepSeek V3 对话模型，免费",
            supports_tools=True,
            tier="light",
            aliases=("ds-chat",),
        ),
        ModelInfo(
            id="deepseek-reasoner",
            name="DeepSeek Reasoner (R1)",
            provider_id="deepseek",
            provider_name="DeepSeek Reasoner",
            description="DeepSeek R1 深度推理，复杂分析/架构/数学",
            supports_tools=True,
            supports_thinking=True,
            tier="pro",
            aliases=("reasoner", "ds-reasoner", "dsr1"),
        ),
        # ── 图片/视频引擎模型（调用 create_image / create_video 端点）──
        ModelInfo(
            id="agnes-image-2.1-flash",
            name="CRUX Image 2.1 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="高清图片生成，支持图生图，高密度输出",
            tier="pro",
            model_type="image",
            aliases=("img-hd",),
        ),
        ModelInfo(
            id="agnes-image-2.1-flash",
            name="CRUX Image 2.1 Flash",
            provider_id="crux",
            provider_name="CRUX AI",
            description="多模态图片生成 + 编辑，图生图/文生图，支持多图参考和标签控制",
            tier="pro",
            model_type="image",
            aliases=("img-edit", "agnes-image"),
        ),
        ModelInfo(
            id="agnes-video-v2.0",
            name="CRUX Video V2.0",
            provider_id="crux",
            provider_name="CRUX AI",
            description="视频生成，支持文生视频和图生视频双模式",
            tier="pro",
            model_type="video",
            aliases=("video", "vid"),
        ),
    ]
    for m in models:
        MODEL_REGISTRY[m.id] = m


_register_defaults()


# ── 查询接口 ──────────────────────────────────────────────


def get_model_info(model_id: str) -> ModelInfo | None:
    """根据模型 ID 查元信息，找不到返回 None。"""
    return MODEL_REGISTRY.get(model_id)


def resolve_model_alias(name: str) -> str | None:
    """将用户输入的别名（light/pro/deepseek/zhipu 等）解析为模型 ID。

    优先查 MODEL_REGISTRY 的别名，再直接查 ID 匹配，最后查 models.json。
    """
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
    """返回所有支持多模态视觉理解的模型 ID 列表（按注册顺序，保持稳定）。

    视觉通道 fallback 链的单一真相源：智谱主视觉 → Agnes 兜底。
    调用方应按任务复杂度选择首选项：
    - 轻量（OCR/描述）→ GLM-4V-Flash（tier=light，免费）
    - 复杂（计数/图表推理）→ glm-4.1v-thinking-flash（tier=pro，免费）
    - 智谱超载时 → agnes-1.5-flash / agnes-2.0-flash 兜底
    """
    return [m.id for m in MODEL_REGISTRY.values() if m.supports_vision]


def model_supports_vision(model_id: str) -> bool:
    """判断指定模型是否支持多模态图片理解。"""
    return model_id in get_vision_models()


# ═══════════════════════════════════════════════════════════════════
# Provider State — 健康追踪 + 冷却
# ═══════════════════════════════════════════════════════════════════


class ProviderState:
    """Tracks which provider is active and which have failed."""

    def __init__(self, active: str, cooldown_sec: float = 30.0) -> None:
        self.active = active
        self.cooldown_sec = cooldown_sec
        self._down_since: dict[str, float] = {}  # provider_id -> timestamp
        self._switch_count: int = 0
        # ── 健康追踪：最近 N 次响应延迟（秒）──
        self._latencies: dict[str, deque] = {}  # provider_id -> deque of float
        self._max_latency_samples = 10

    def record_latency(self, provider_id: str, elapsed_sec: float):
        """Record a response latency sample for the given provider."""
        if provider_id not in self._latencies:
            self._latencies[provider_id] = deque(maxlen=self._max_latency_samples)
        self._latencies[provider_id].append(elapsed_sec)

    def health_hint(self) -> str | None:
        """Check active provider health, return warning string or None.

        Warns if the active provider's average latency is > 15s over
        recent samples (indicating chronic slowness, not a one-off spike).
        """
        samples = self._latencies.get(self.active)
        if not samples or len(samples) < 3:
            return None  # not enough data

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
        return [p for p in ordered if not self.is_down(p)]

    def available_by_latency(self, provider_ids: list[str]) -> list[str]:
        """Return available providers sorted by average latency (fastest first).

        When choosing between equally-capable providers for the same model tier,
        prefer the one with lower historical latency. Active provider gets a
        slight boost (treated as 20% faster than measured) to avoid unnecessary
        flapping.
        """
        available = self.available(provider_ids)
        if len(available) <= 1:
            return available

        def avg_latency(pid: str) -> float:
            samples = self._latencies.get(pid, deque())
            if not samples:
                return 999.0
            avg = sum(samples) / len(samples)
            # Active provider gets 20% speed boost to avoid flapping
            if pid == self.active:
                avg *= 0.8
            return avg

        return sorted(available, key=avg_latency)


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

        with open(self.config_path, encoding="utf-8") as f:
            cfg = json.load(f)

        self.providers = cfg.get("providers", {})
        fallback_cfg = cfg.get("fallback", {})
        self.fallback_priority = fallback_cfg.get("priority", [])
        self.state.active = cfg.get("active", "crux")

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
        """Manually switch active provider."""
        if provider_id in self.providers:
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

    def fallback(self) -> bool:
        """Switch to next available provider. Returns True on success."""
        available = self.state.available(list(self.providers.keys()))
        for pid in available:
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

    def create_client(self, provider_id: str | None = None):
        """Create an CruxClient for the given or active provider."""
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
            logger.error(
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
                return self.create_client(fallback)
            raise NoProviderAvailable(f"No API key for provider '{pid}'")

        return CruxClient(api_key=api_key, base_url=provider["base_url"])

    def handle_failure(self, failed_provider: str, status_code: int) -> tuple[object | None, str | None]:
        """Called when a provider request fails. Returns (new_client, new_provider_id)
        if failover succeeded, or (None, None) if all providers exhausted.
        """
        self.state.mark_down(failed_provider)

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


def get_provider_manager() -> ProviderManager:
    global _mgr
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
