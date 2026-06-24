"""CRUX 全局智能任务路由器 — 根据任务复杂度/类型自动选择最优模型/供应商。

设计原则:
- 规则引擎 + 启发式分类（不调 LLM），零延迟零成本
- 命令级路由查静态表，自然语言用关键词 + 上下文感知
- 跨供应商切换复用 ProviderManager.create_client()
- 不动摇 toggle_agent_mode / load_skill 的确定性模型选择（tool-calling 需要）
- 所有路由决策都有 reason 字段，供 badge 行 / ui 展示，用户知情

接入点:
- ui/mixins/shared.py:_stream_chat()  → 自然语言对话路由
- ui/mixins/engineering.py             → /plan /sub /refactor 等深度命令
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = [
    'TaskProfile',
    'RouteDecision',
    'classify',
    'route_command',
    'resolve',
    'apply',
    'route',
]


# ── 任务画像 ───────────────────────────────────────────────

class TaskProfile(Enum):
    """任务复杂度/类型画像。"""
    CHAT = "chat"            # 简单对话 / 问答
    QUICK_FIX = "quick_fix" # bug修复 / 小改动
    CODING = "coding"        # 代码实现（code_mode + tools）
    DEEP = "deep"            # 架构 / 复杂分析（需深度推理 + 大上下文）
    CREATIVE = "creative"    # 创意生产（图 / 视频 / showrunner）
    SKIP = "skip"            # 不干预，保持当前模型


# ── 路由决策 ───────────────────────────────────────────────

@dataclass
class RouteDecision:
    """单次路由决策结果。"""
    profile: TaskProfile
    model_id: str | None = None   # None = 不改 session.model
    reason: str = ""              # 给 badge 行显示的路由理由
    switch_client: bool = False  # 是否需要切 client（跨供应商）


# ── 模型/供应商映射 ─────────────────────────────────────────

# 各 TaskProfile 的推荐模型 ID
# v5.0+: DeepSeek 双档化（同 key 同 base_url），按 Claude Haiku/Sonnet/Opus 分层：
# - CHAT (闲聊/问答) → deepseek-v4-flash（轻量档，对标 Haiku，省 ~50% 成本）
# - QUICK_FIX/CODING/DEEP/CREATIVE → deepseek-v4-pro（深度思考 + 1M 上下文，对标 Sonnet/Opus）
# 视觉走独立通道（agnes-1.5-flash），不经 router，不在此表。
# 注：flash 与 pro 同属 deepseek 供应商，CHAT→flash 不触发 client 切换，零成本降档。
_PROFILE_MODEL: dict[TaskProfile, str] = {
    TaskProfile.CHAT: "deepseek-v4-flash",
    TaskProfile.QUICK_FIX: "deepseek-v4-pro",
    TaskProfile.CODING: "deepseek-v4-pro",
    TaskProfile.DEEP: "deepseek-v4-pro",
    TaskProfile.CREATIVE: "deepseek-v4-pro",
    TaskProfile.SKIP: "",  # 不干预
}


def _detect_provider(model_id: str, mgr: object | None = None) -> str:
    """根据模型 ID 查找所属供应商 ID。

    优先查 MODEL_REGISTRY（单一真相源），缓存未命中再遍历 models.json。
    mgr 参数避免 apply() 内重复 load()。
    """
    # 1. 优先查 MODEL_REGISTRY
    try:
        from core.provider import MODEL_REGISTRY
        info = MODEL_REGISTRY.get(model_id)
        if info is not None:
            return info.provider_id
    except Exception:
        pass

    # 2. 回退：从 models.json 遍历反查
    try:
        from core.provider import get_provider_manager
        _mgr = mgr or get_provider_manager()
        if not _mgr.providers:
            _mgr.load()
        for pid, pdata in _mgr.providers.items():
            models = pdata.get("models", {})
            if isinstance(models, dict):
                if model_id in models.values():
                    return pid
    except Exception:
        pass
    return ""


# ── 命令路由表（静态，零 LLM 消耗）─────────────────────────

# key: 命令名, value: (TaskProfile, 推荐模型 ID, 理由)
# None model = 保持当前模型不切（如 showrun 已由 handler 自己设好）
COMMAND_ROUTE_MAP: dict[str, tuple[TaskProfile, str | None, str]] = {
    "plan":     (TaskProfile.DEEP,      "deepseek-v4-pro",  "深度推理任务 → 切至 DeepSeek（1M 上下文）"),
    "sub":      (TaskProfile.DEEP,      "deepseek-v4-pro",  "子智能体需要强推理 → 切至 DeepSeek"),
    "refactor": (TaskProfile.DEEP,      "deepseek-v4-pro",  "跨文件重构需要大上下文 → 切至 DeepSeek"),
    "team":     (TaskProfile.DEEP,      None,               "多智能体协调 → 保持当前模型"),
    "showrun":  (TaskProfile.CREATIVE,   None,               "创意流水线 → 保持当前模型"),
    "self":     (TaskProfile.CODING,    None,               "自诊断 → 保持当前模型"),
    # 以下命令不需要 LLM 或不应干预
    "help":     (TaskProfile.SKIP, None, ""),
    "model":    (TaskProfile.SKIP, None, ""),
    "thinking": (TaskProfile.SKIP, None, ""),
    "code":     (TaskProfile.SKIP, None, ""),
    "agent":    (TaskProfile.SKIP, None, ""),
    "tools":    (TaskProfile.SKIP, None, ""),
    "clear":    (TaskProfile.SKIP, None, ""),
    "exit":     (TaskProfile.SKIP, None, ""),
    "quit":     (TaskProfile.SKIP, None, ""),
    "q":        (TaskProfile.SKIP, None, ""),
    "compress": (TaskProfile.SKIP, None, ""),
    "project":  (TaskProfile.SKIP, None, ""),
    "todo":     (TaskProfile.SKIP, None, ""),
    "commit":   (TaskProfile.SKIP, None, ""),
    "changelog": (TaskProfile.SKIP, None, ""),
    "audit":    (TaskProfile.SKIP, None, ""),
    "rules":    (TaskProfile.SKIP, None, ""),
    "automate": (TaskProfile.SKIP, None, ""),
    "provider": (TaskProfile.SKIP, None, ""),
    "evolve":   (TaskProfile.SKIP, None, ""),
    "know":     (TaskProfile.SKIP, None, ""),
    "skill":    (TaskProfile.SKIP, None, ""),
    "img":      (TaskProfile.SKIP, None, ""),
    "video":    (TaskProfile.SKIP, None, ""),
    "vision":   (TaskProfile.SKIP, None, ""),
    "deploy":   (TaskProfile.SKIP, None, ""),
}


# ── 自然语言分类器（规则引擎）───────────────────────────────

# 关键词 → TaskProfile 映射（优先级从高到低匹配）
_DEEP_KEYWORDS: list[str] = [
    r"重构", r"架构", r"系统级", r"整体设计", r"全面分析",
    r"重新设计", r"方案", r"技术选型", r"可行性",
    r"性能优化.*整体", r"迁移.*系统", r"替换.*框架",
    r"review.*全", r"审查.*全部",
]

_QUICK_FIX_KEYWORDS: list[str] = [
    r"bug", r"修复", r"改一下", r"调一下", r"小改",
    r"fix", r"patch", r"hotfix", r"补丁",
    r"换.*图标", r"换.*颜色", r"改.*名字", r"改.*文案",
    r"typo", r"拼写",
]

_CREATVE_KEYWORDS: list[str] = [
    r"生成.*图", r"生成.*视频", r"画", r"画一个",
    r"创建.*图", r"创建.*视频", r"做.*海报",
    r"文生图", r"图生图", r"图生视频", r"文生视频",
    r"showrun", r"制片", r"分镜",
]

_CODE_KEYWORDS: list[str] = [
    r"实现", r"写.*函数", r"写.*方法", r"写.*类",
    r"加.*功能", r"新增.*接口", r"添加.*接口",
    r"写.*测试", r"加.*测试",
    r"代码", r"编程", r"开发",
    # 注意：不含 \.py/\.js/\.ts 等扩展名——文件路径场景由文本特征分析阶段处理
    r"(?<!\w)def\s", r"(?<!\w)function\s",
]

# 文件路径正则（含 Windows 路径和 Unix 路径）
_FILE_PATH_RE = re.compile(
    r'(?:[A-Za-z]:[\\/][^\s:?*"<>|]+\.(?:py|js|ts|md|json|yaml|yml|toml|cfg|ini|sh|bat)'
    r'|[~/][^\s:?*"<>|]+\.(?:py|js|ts|md|json|yaml|yml|toml|cfg|ini|sh|bat))',
    re.IGNORECASE,
)

# 代码片段检测（多行缩进 + 常见关键字）
_CODE_BLOCK_RE = re.compile(
    r'(?:def |class |import |from |async def |const |let |function |export )',
    re.MULTILINE,
)

# 深度请求的特征：长文本 + 多段落（可能是需求文档/设计文档）
_LONG_TEXT_THRESHOLD = 500


def classify(text: str, session: ChatSession | None = None) -> TaskProfile:
    """分析自然语言文本，返回任务画像。

    纯规则 + 启发式，不调 LLM，零延迟零成本。
    匹配优先级: 会话上下文 > 关键词 > 文本特征 > 默认。
    """
    if not text or not text.strip():
        return TaskProfile.SKIP

    text_lower = text.lower().strip()
    text_len = len(text)

    # ── 1. 会话上下文感知（最高优先级）──
    # 已在 agent_mode / active_skill 中 → 跟随其模式，不额外分类
    if session is not None:
        if getattr(session, 'agent_mode', False):
            return TaskProfile.CODING
        if getattr(session, 'active_skill', ''):
            skill = session.active_skill
            if skill in ("showrunner", "comfyui-bridge"):
                return TaskProfile.CREATIVE
            # 其他技能按 CODING 处理
            return TaskProfile.CODING

    # ── 2. 关键词匹配（按优先级从高到低）──
    # DEEP > CREATIVE > QUICK_FIX > CODING > CHAT

    for pattern in _DEEP_KEYWORDS:
        if re.search(pattern, text_lower):
            return TaskProfile.DEEP

    for pattern in _CREATVE_KEYWORDS:
        if re.search(pattern, text_lower):
            return TaskProfile.CREATIVE

    for pattern in _QUICK_FIX_KEYWORDS:
        if re.search(pattern, text_lower):
            return TaskProfile.QUICK_FIX

    for pattern in _CODE_KEYWORDS:
        if re.search(pattern, text_lower):
            return TaskProfile.CODING

    # ── 3. 文本特征分析 ──

    # 含文件路径 → 代码相关（路径多 = 可能跨文件 → DEEP）
    file_paths = _FILE_PATH_RE.findall(text)
    if file_paths:
        if len(file_paths) >= 3 or text_len > _LONG_TEXT_THRESHOLD:
            return TaskProfile.DEEP
        return TaskProfile.QUICK_FIX

    # 含代码片段 → CODING
    if _CODE_BLOCK_RE.search(text):
        return TaskProfile.CODING

    # 长文本（可能是需求文档/设计文档）→ DEEP
    if text_len > _LONG_TEXT_THRESHOLD:
        # 检查是否是代码粘贴（多行 + 高缩进比）
        lines = text.split('\n')
        code_lines = sum(1 for l in lines if l.strip().startswith((' ', '\t', 'def ', 'class ', 'import ', 'from ')))
        if code_lines > len(lines) * 0.5:
            return TaskProfile.CODING
        return TaskProfile.DEEP

    # ── 4. code_mode 上下文 ──
    if session is not None and getattr(session, 'code_mode', False):
        return TaskProfile.CODING

    # ── 5. 默认：保持当前模型 ──
    return TaskProfile.SKIP


# ── 路由决策合成 ───────────────────────────────────────────

def route_command(cmd_key: str, arg: str, session: ChatSession | None) -> RouteDecision:
    """命令级路由：查静态表。

    未在表中的命令 → SKIP（不干预）。
    """
    entry = COMMAND_ROUTE_MAP.get(cmd_key)
    if entry is None:
        return RouteDecision(profile=TaskProfile.SKIP)

    profile, model_id, reason = entry

    # model_id 为 None 表示保持当前
    if model_id is None:
        return RouteDecision(profile=profile, reason=reason)

    return RouteDecision(profile=profile, model_id=model_id, reason=reason)


def resolve(profile: TaskProfile | str, session: ChatSession | None) -> RouteDecision:
    """将 TaskProfile 解析为具体的 RouteDecision。

    考虑当前模型是否已经匹配（避免无意义的切换）。
    接受 TaskProfile 枚举或字符串值（如 "quick_fix"），方便外部直接调用。
    """
    # 兼容字符串输入（如 git_cmds 传入 "quick_fix"）
    if isinstance(profile, str):
        try:
            profile = TaskProfile(profile)
        except ValueError:
            return RouteDecision(profile=TaskProfile.SKIP)

    if profile == TaskProfile.SKIP:
        return RouteDecision(profile=TaskProfile.SKIP)

    target_model = _PROFILE_MODEL.get(profile, "")
    if not target_model:
        return RouteDecision(profile=TaskProfile.SKIP)

    # 当前模型已经匹配 → 不切
    if session is not None and session.model == target_model:
        return RouteDecision(profile=profile, reason="")

    # 构建理由
    reason_map = {
        TaskProfile.CHAT: "简单对话 → 切至 DeepSeek Flash（快速响应，省成本）",
        TaskProfile.QUICK_FIX: "快速修复任务 → 切至 DeepSeek（tool-calling + 思考）",
        TaskProfile.CODING: "代码实现任务 → 切至 DeepSeek（tool-calling + 思考）",
        TaskProfile.DEEP: "复杂分析任务 → 切至 DeepSeek（1M 上下文深度推理）",
        TaskProfile.CREATIVE: "创意生产任务 → 切至 DeepSeek（tool-calling + 思考）",
    }
    reason = reason_map.get(profile, f"任务类型 {profile.value} → 切至 {target_model}")
    return RouteDecision(profile=profile, model_id=target_model, reason=reason)


def apply(decision: RouteDecision, session: ChatSession) -> None:
    """执行路由决策：改 session.model、必要时切 session.client、刷新 system prompt。

    不改 toggle_agent_mode / load_skill 的确定性选择——只在 route() 流程中调用。

    健壮性保证：
    - 跨供应商切换时校验返回 client 的 base_url 与目标供应商一致，
      不一致（create_client 内部静默 fallback 到其他供应商）则回滚，避免
      model/client 不匹配导致 API 报错。
    - session.messages 空列表防御（避免 IndexError）。
    """
    if decision.profile == TaskProfile.SKIP or decision.model_id is None:
        return

    if decision.model_id == session.model:
        return  # 已经是目标模型

    old_model = session.model

    # 跨供应商切换？单次 load()，复用给 _detect_provider
    mgr = None
    current_pid = ""
    target_pid = ""
    try:
        from core.provider import get_provider_manager
        mgr = get_provider_manager()
        if not mgr.providers:
            mgr.load()
        current_pid = _detect_provider(session.model, mgr)
        target_pid = _detect_provider(decision.model_id, mgr)
    except Exception:
        pass

    if current_pid and target_pid and current_pid != target_pid:
        # 目标供应商在 models.json 中的 base_url，用于一致性校验
        target_base_url = ""
        try:
            target_base_url = (mgr.providers.get(target_pid, {}) or {}).get("base_url", "")
        except Exception:
            pass

        try:
            new_client = mgr.create_client(target_pid)
            # 一致性校验：若 create_client 内部 fallback 到其他供应商，
            # new_client.base_url 会与目标供应商不匹配 → 回滚，保留旧 client。
            new_base = getattr(new_client, "base_url", "") or ""
            # 统一去掉末尾斜杠再比较
            if target_base_url and new_base.rstrip("/") != target_base_url.rstrip("/"):
                # fallback 了，不切，保留当前 client/model
                return
            session.client = new_client
            decision.switch_client = True
        except Exception:
            # 切换失败（无 Key / 供应商不可用）→ 保留当前供应商，不改 model
            return

    session.model = decision.model_id

    # 刷新系统提示词（让 AI 知道当前供应商/模型）
    # 空列表防御：messages 为空时插入而非替换
    if session.messages:
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
    else:
        session.messages.insert(0, {"role": "system", "content": session._build_system_prompt()})


# ── 顶层统一入口 ──────────────────────────────────────────

def route(text: str, session: ChatSession) -> RouteDecision:
    """顶层路由入口。

    自动判断 text 是自然语言还是斜杠命令，分别走 classify / route_command，
    然后 resolve → 返回 RouteDecision。

    调用方负责在需要时调用 apply() 执行决策。
    """
    stripped = text.strip()

    # 斜杠命令 → 走命令路由表
    if stripped.startswith("/"):
        cmd_key, _, arg = stripped[1:].partition(" ")
        return route_command(cmd_key.strip(), arg.strip(), session)

    # 自然语言 → 分类
    profile = classify(stripped, session)
    return resolve(profile, session)
