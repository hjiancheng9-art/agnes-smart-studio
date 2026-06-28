"""System Prompt Builder — 从 chat.py 提取的独立模块。

管理 CHAT/CODE 模板 + 20 层谱系注入 + 缓存逻辑。
ChatSession._build_system_prompt() 调用 build_system_prompt()。
向后兼容：chat.py 仍可通过 __all__ 导出 CHAT_SYSTEM_PROMPT / CODE_SYSTEM_PROMPT。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("crux.chat_prompt")

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CODE_SYSTEM_PROMPT",
    "PromptCache",
    "build_system_prompt",
    "get_cached_prompt",
    "set_cached_prompt",
]

# ── 模板（从 chat.py 移出，单一真源）──────────────────────

CHAT_SYSTEM_PROMPT = """你是 {provider_name} 智能助手，当前运行在 {model_name} 模型上。你擅长：
- 日常问答、创意写作、知识解释、方案讨论
- 当用户明确想生成图片时，调用 generate_image 工具
- 当用户明确想生成视频/动画时，调用 generate_video 工具
- 普通对话不要调用任何工具

重要约束：
- generate_image / generate_video 每轮对话最多调用 1 次，生成后必须立即总结结果给用户
- 不要在生成后调用对比/评估工具，更不要因评分不理想而重新生成
- 工具执行成功后，直接用文字回复用户，不要再调用任何工具

风格：简洁、中文优先、回答到位。如果用户询问你使用的模型，直接告知当前运行的是 {model_name}。"""

CODE_SYSTEM_PROMPT = """你是 {provider_name} 编程助手，当前运行在 {model_name} 模型上。
你是一位资深全栈工程师，擅长：
- Python、JavaScript/TypeScript、Go、Rust、Java、C/C++ 等主流语言
- Web 开发（React、Vue、Node.js、FastAPI、Django）
- 数据库设计、API 设计、系统架构
- 调试、性能优化、代码审查
- 所有回答附带完整可运行代码，标注语言

## 工作纪律（探索-计划-执行三段式）
回答编码任务时遵循以下顺序，简单任务可压缩，但探索段永不可省：
1. **探索**：先读相关文件理解现状，不凭记忆猜 API 签名和库行为
2. **计划**：复杂任务用 ≤5 步概述方案，每步可独立验证
3. **执行**：按计划实施，每步完成后说明"已完成 + 验证方式"

## 核心约束
- **事实优先**：不确定的 API/配置/默认值，先读代码或文档验证，绝不编造
- **最小改动**：只改必须改的行，不顺手重构无关代码，不为未来需求过度抽象
- **完整闭环**：一个任务必须含实现+测试+验证才算完成；修复 error 后必须验证
- **删除前搜索**：删除函数/变量/文件前，先 grep 全项目确认无引用
- **失败如实报**：测试失败就报失败，跳过的步骤明说跳过了

## 输出规范
- 代码块必须标注语言（```python、```javascript 等）
- 复杂问题分步骤讲解：分析 → 方案 → 代码 → 说明
- 优先给出最简实现，不过度设计
- 如需调用图片/视频工具，明确告知用户用 /img 或 /video 命令
- 如果用户询问你使用的模型，直接告知当前运行的是 {model_name}，由 {provider_name} 提供"""


# ── 模块级缓存（从 chat.py _cached_prompt 提升）────────

class PromptCache:
    """Prompt 缓存：避免每轮对话 10+ import 链重建。"""

    def __init__(self):
        self.key = ""
        self.prompt = ""

    def get(self, cache_key: str) -> str | None:
        if self.key == cache_key and self.prompt:
            return self.prompt
        return None

    def set(self, cache_key: str, prompt: str) -> None:
        self.key = cache_key
        self.prompt = prompt

    def invalidate(self) -> None:
        self.key = ""
        self.prompt = ""


# 全局单例
_cache = PromptCache()


def get_cached_prompt() -> PromptCache:
    return _cache


def set_cached_prompt(key: str, prompt: str) -> None:
    _cache.set(key, prompt)


# ── 谱系注入注册表（每项: (模块路径, 函数名, 描述)）───
# CHAT mode: 7 useful layers (trimmed from 17 decorative spectrum layers)
_SPECTRUM_INJECTIONS: list[tuple[str, str, str]] = [
    ("core.lore.claude_dna", "get_claude_dna_prompt", "Claude DNA"),
    ("core.rules", "get_rules", "规则注入"),
    ("core.marketplace", "get_marketplace", "技能市场"),
    ("core.orchestra", "get_orchestra", "调度总览"),
    ("core.prompt_lab", "get_prompt_lab", "Prompt Lab"),
    ("core.seven_beasts_fusion", "get_fusion_prompt", "七兽融合"),
    ("core.beast_wiring", "get_wiring_summary", "五兽躯体"),
]

_CODE_SPECTRUM_INJECTIONS: list[tuple[str, str, str]] = [
    ("core.lore.claude_dna", "get_claude_dna_prompt", "Claude DNA"),
    ("core.rules", "get_rules", "rules injection"),
    ("core.marketplace", "get_marketplace", "marketplace"),
]


# ── 注入模块文件指纹（改任意谱系文件自动破缓存）─────────

def _get_injections_fingerprint() -> str:
    """所有注入模块 + core/lore/ 目录下 .py 的 mtime 指纹。

    任何 lore 文件被编辑后，下次 build_system_prompt 自动重建缓存，
    无需手动重启进程。
    """
    import hashlib
    import os

    mtimes: list[str] = []
    seen = set()
    for mod_path, _, _ in _SPECTRUM_INJECTIONS + _CODE_SPECTRUM_INJECTIONS:
        if mod_path in seen:
            continue
        seen.add(mod_path)
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            f = getattr(mod, "__file__", None)
            if f:
                mtimes.append(str(int(os.path.getmtime(f))))
        except Exception:
            pass
    # 兜底：lore 目录下所有 .py（含新增/重命名文件）
    lore_dir = os.path.join(os.path.dirname(__file__), "lore")
    if os.path.isdir(lore_dir):
        for f in sorted(os.listdir(lore_dir)):
            if f.endswith(".py"):
                mtimes.append(str(int(os.path.getmtime(os.path.join(lore_dir, f)))))
    if not mtimes:
        return ""
    return hashlib.md5("|".join(mtimes).encode()).hexdigest()[:12]


# ── 公共构建函数 ────────────────────────────────────────

def build_system_prompt(
    model: str,
    provider_name: str,
    code_mode: bool = False,
    browser_enabled: bool = False,
    notebook_enabled: bool = False,
    audio_enabled: bool = False,
    active_skill_rules_hash: str = "",
    skills_auto_prompt_manager=None,
) -> str:
    """构建完整 system prompt — ChatSession 的独立调用入口。

    Args:
        model: 当前模型 ID
        provider_name: 供应商人类可读名
        code_mode: 是否为代码模式
        browser_enabled: Browser Companion 已启用
        notebook_enabled: Notebook 工具已启用
        audio_enabled: 音频工具已启用
        active_skill_rules_hash: 当前活跃规则的 hash（纳入缓存 key）
        skills_auto_prompt_manager: SkillManager 实例（用于 auto_skills_prompt）

    Returns:
        完整的系统提示词字符串。
    """
    template = CODE_SYSTEM_PROMPT if code_mode else CHAT_SYSTEM_PROMPT
    cache_key = (
        f"{provider_name}|{model}|{code_mode}"
        f"|b{browser_enabled}|n{notebook_enabled}|a{audio_enabled}"
        f"|{active_skill_rules_hash}"
        f"|{_get_injections_fingerprint()}"
    )

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    base = template.format(provider_name=provider_name, model_name=model)
    base += (
        "\n\n## 回答质量规范\n"
        "- 直接回答，不要重复用户的问题\n"
        "- 不要在 3 轮内重复相同内容\n"
        "- 不要逐字复述已有的上下文\n"
        "- 回答尽量在 2 段以内，简洁到位\n"
        "- 避免无意义的寒暄和套话"
    )

    # 谱系注入：CODE 模式只注 3 层，CHAT 模式注全部
    injections = _CODE_SPECTRUM_INJECTIONS if code_mode else _SPECTRUM_INJECTIONS
    for mod_path, func_name, label in injections:
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            fn = getattr(mod, func_name, None)
            if fn is None:
                continue
            # 根据函数签名智能调用
            if func_name == "get_rules":
                base += fn().inject_prompt()
            elif func_name == "get_marketplace":
                base += "\n\n" + fn().summary()
            elif func_name == "get_orchestra":
                base += "\n\n" + fn().summary()
            elif func_name == "get_prompt_lab":
                base += fn().get_active_instructions()
            else:
                # 谱系 prompt 函数（get_fusion_prompt / get_wiring_summary 等）
                result = fn()
                if isinstance(result, str) and result:
                    base += "\n\n" + result
        except (ImportError, OSError) as e:
            logger.debug("spectrum injection skipped (%s): %s", label, e)
        except Exception as e:
            logger.debug("spectrum injection error (%s): %s", label, e)

    # 条件注入：browser / notebook / audio
    if browser_enabled:
        base += (
            "\n\n## Browser Companion 网页生成\n"
            "你可以通过 browser_generate 在 8 个网页平台上全自动生成图片/视频：\n"
            "可灵(Kling) / 即梦(Jimeng) / Runway / Luma / DALL-E / Gemini / Opal / Veo\n"
            "优先用官方 API（需配置 API Key），无 Key 时自动降级到 Playwright 浏览器自动化。\n"
            "首次使用某个平台前需 browser_setup 登录一次，之后 session 自动保存。\n"
            "用 browser_providers 查看可用平台状态，browser_check 查询任务进度。"
        )
    if notebook_enabled:
        base += (
            "\n\n## Notebook 工具\n"
            "你可以操作 Jupyter notebook (.ipynb)：打开/编辑/执行代码单元格/保存。\n"
            "适合数据分析、实验记录、可视化等数据科学场景。"
        )
    if audio_enabled:
        base += (
            "\n\n## 音频工具\n"
            "你可以生成音频内容：tts_narration(文字转语音旁白)、generate_bgm(背景音乐)、\n"
            "generate_sfx(音效)、audio_mixdown(多轨混音)。\n"
            "所有输出保存到 output/audio/。补齐 Showrunner 旁白+BGM 音轨。"
        )

    # Skill 三态：注入所有 trigger=auto 的技能 prompt
    if skills_auto_prompt_manager is not None:
        base = skills_auto_prompt_manager(base)

    # 存入缓存
    _cache.set(cache_key, base)
    return base
