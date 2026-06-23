"""Agnes 模式 Badge 系统 — 统一状态可视化。

唯一合法的 session 状态 → 彩色标签 转换器。所有"当前处于什么模式"的
终端展示都走这里，避免状态信息散落在多处提示词拼接里。

风格: 彩色标签流（每段独立着色，用 · 分隔）
  🤖 Agent · 💭 Think · 🎬 showrunner · ⚡ agnes-2.0-flash

接入点:
- ui/mixins/shared.py:_mode_hint()      → 输入提示符后的简版 badge
- ui/mixins/shared.py:_stream_chat()     → 每条 AI 回复正上方的 badge 头
- ui/mixins/engineering.py:_chat_plan()  → /plan 独立渲染路径
- 各 toggle handler                       → 切换后打印醒目 banner

渲染契约: 本模块只 print 纯文本行，绝不触碰 StreamingRenderer 的
transient Live 或单一落盘点（commit）。badge 行在 renderer.start() 之前
打印，不会被 transient 浮层干扰。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.display import COLORS, console

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = [
    'Badge',
    'session_badges',
    'render_badge_line',
    'render_badge_plain',
    'print_reply_header',
    'print_mode_banner',
    'print_route_reason',
]


# ── 数据模型 ───────────────────────────────────────────────

class Badge:
    """单个状态标签：图标 + 文本 + 颜色。"""

    __slots__ = ('icon', 'text', 'color')

    def __init__(self, icon: str, text: str, color: str):
        self.icon = icon
        self.text = text
        self.color = color

    def render(self, *, dim: bool = False) -> str:
        """返回 Rich markup 片段，如 '[magenta]🤖 Agent[/]'。"""
        style = self.color if not dim else f"dim {self.color}"
        return f"[{style}]{self.icon} {self.text}[/]"


# ── 供应商简称映射（模型 ID → 人类可读供应商标签）──────────

_PROVIDER_SHORT = {
    "Agnes AI": "Agnes",
    "DeepSeek": "DeepSeek",
    "SiliconFlow": "SiliconFlow",
    "Moonshot": "Kimi",
}


def _model_label(session: "ChatSession") -> tuple[str, str]:
    """返回 (模型显示文本, 颜色)。模型名 + 供应商简称（去重）。"""
    model = getattr(session, 'model', '') or 'unknown'
    try:
        from core.provider import get_provider_name, get_model_info
        info = get_model_info(model)
        label = (info.name if info and info.name and info.name != model else model)
        provider = get_provider_name(model)
        # 供应商简称：优先用映射表，否则用原 provider 名
        short = _PROVIDER_SHORT.get(provider, "") if provider != model else ""
        # 去重：简称已是 label 子串（大小写不敏感）就不重复拼接
        if short and short.lower() not in label.lower():
            label = f"{label} · {short}"
    except Exception:
        label = model
    # 默认模型用 muted，pro/agent 模型用 teal 更醒目
    color = COLORS['muted'] if model in ('agnes-1.5-flash',) else "#26A69A"
    return label, color


# ── 核心：session → badge 列表 ────────────────────────────

def session_badges(session: "ChatSession | None") -> list[Badge]:
    """从 session 状态生成有序 badge 列表。

    顺序固定: 模式(code/agent) → 思考 → 技能 → 模型/供应商。
    None 或菜单等无 session 场景返回空列表。
    """
    if session is None:
        return []

    badges: list[Badge] = []

    # 模式（互斥显示语义：code 与 agent 是两个独立 toggle，都可能是 True）
    if getattr(session, 'code_mode', False):
        badges.append(Badge("🔧", "Code", COLORS['primary']))
    if getattr(session, 'agent_mode', False):
        badges.append(Badge("🤖", "Agent", COLORS['accent']))

    # 深度思考
    if getattr(session, 'enable_thinking', False):
        badges.append(Badge("💭", "Think", COLORS['warning']))

    # 已加载技能（优先用技能自带 icon）
    skill = getattr(session, 'active_skill', '')
    if skill:
        icon = "🎬"
        try:
            mgr = getattr(session, 'skills', None)
            if mgr is not None:
                s = mgr._available.get(skill) if hasattr(mgr, '_available') else None
                if s and getattr(s, 'icon', ''):
                    icon = s.icon
        except Exception:
            pass
        badges.append(Badge(icon, skill, COLORS['success']))

    # 模型 / 供应商（始终显示）
    model_text, model_color = _model_label(session)
    badges.append(Badge("⚡", model_text, model_color))

    return badges


# ── 渲染入口 ───────────────────────────────────────────────

def render_badge_line(session: "ChatSession | None", *, dim: bool = True) -> str:
    """返回完整 badge 行的 Rich markup 字符串（供 console.print 用）。

    各段用 ' · ' 分隔，整体可选 dim 化（用于回复头，不抢眼）。
    """
    badges = session_badges(session)
    if not badges:
        return ""
    sep = " [dim]·[/] "
    return sep.join(b.render(dim=dim) for b in badges)


def render_badge_plain(session: "ChatSession | None") -> str:
    """返回纯文本 badge 行（供 prompt_toolkit 输入提示符用）。

    prompt_toolkit 不解析 Rich markup，给它 Rich 标签会把
    '[#26A69A]⚡...[/]' 当原文显示出来。这里输出干净的
    '🤖 Agent · 💭 Think · ⚡ Agnes 2.0 Flash' 纯文本。
    """
    badges = session_badges(session)
    if not badges:
        return ""
    return " · ".join(f"{b.icon} {b.text}" for b in badges)


def print_reply_header(session: "ChatSession | None") -> None:
    """在每条 AI 回复正上方打印 badge 行（dim 化）。

    在 StreamingRenderer.start() 之前调用——此时没有 transient Live 浮层，
    纯 console.print 直接落盘，不受渲染契约的单一落盘点约束。
    """
    line = render_badge_line(session, dim=True)
    if line:
        console.print(line)


def print_mode_banner(session: "ChatSession | None") -> None:
    """模式切换时打印醒目 badge 横幅（非 dim）。

    让用户在 toggle /load_skill /switch_model 之后立刻看到新状态。
    """
    badges = session_badges(session)
    if not badges:
        return
    line = " [dim]·[/] ".join(b.render(dim=False) for b in badges)
    console.print(f"  {line}")


def print_route_reason(reason: str) -> None:
    """显示路由决策理由（dim 灰色，不抢眼）。

    在 print_reply_header 之后调用，让用户知道 router 为什么切了模型。
    效果: '  ↳ 多文件重构任务 → 切至 DeepSeek（1M 上下文深度推理）'
    """
    if reason:
        console.print(f"  [dim]↳ {reason}[/]")
