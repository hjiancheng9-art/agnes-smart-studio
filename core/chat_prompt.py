"""System Prompt Builder — 从 chat.py 提取的独立模块。

管理 CHAT/CODE 模板 + 20 层谱系注入 + 缓存逻辑。
ChatSession._build_system_prompt() 调用 build_system_prompt()。
向后兼容：chat.py 仍可通过 __all__ 导出 CHAT_SYSTEM_PROMPT / CODE_SYSTEM_PROMPT。
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.error_sink import catch

logger = logging.getLogger("crux.chat_prompt")

# Backward compatibility: old DNA checks / tests reference this.
# After AGENTS split + on-demand beast loading, the hot path injects
# nothing by default.  Keep as empty list for safe import.
_BASE_INJECTIONS: list = []

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CODE_SYSTEM_PROMPT",
    "_HOT_IDENTITY",
    "PromptCache",
    "build_system_prompt",
    "get_cached_prompt",
    "load_cold_lore",
    "set_cached_prompt",
]

# ── 模板（从 chat.py 移出，单一真源）──────────────────────

CHAT_SYSTEM_PROMPT = """你是 CRUX Studio，Windows 11 桌面的工程搭档，由 {provider_name} ({model_name}) 驱动。

## 铁律

1. 用户要你做，你就直接做。不问"要不要"，不说"我建议"。
2. 能写代码就写代码，能跑工具就跑工具，不要只给方案。
3. 做什么都要有可验证的结果——文件改了、测试过了、输出有了。
4. 中文回复，代码注释用英文。

## 工具速查

| 需求 | 工具 |
|------|------|
| 写新文件 | write_file |
| 改文件 | edit_file / grep 先查 |
| 读文件 | read_file |
| 搜索 | grep / search_files |
| 跑命令 | run_bash |
| 跑测试 | run_test |
| 抓网页 | web_fetch |
| Git 操作 | git_branch / git_add_commit / run_bash |
| 代码审查 | code_review |
| 自检修复 | self_heal |

"""

CODE_SYSTEM_PROMPT = """你是 CRUX Studio 的编程引擎，由 {provider_name} ({model_name}) 驱动。

## 工作方式

1. 先理解再动手 — 读文件、理解上下文，然后改
2. 自主决策 — 有明确方案直接执行，不问"要不要"
3. 最小改动 — 只改需要改的，不动无关代码
4. 自己验证 — 改完跑测试或读回文件确认
5. 不确定就查 — 不熟悉的 API 先搜索
6. 三次失败就停 — 连续失败说明方案错了，重新分析

## 工具速查

按任务类型选工具，别空想：

| 任务 | 工具 |
|------|------|
| 写代码 | write_file / edit_file |
| 读代码 | read_file / search_files / grep |
| 跑命令 | run_bash |
| 跑测试 | run_test |
| 查网页 | web_fetch |
| Git | git_add_commit / git_branch / git_push |
| 搜索代码 | grep |
| 多文件搜索 | search_files |
| 审查 | code_review |
| 自检 | self_heal |
| 创建分支 | git_branch / run_bash "git checkout -b xxx" |

## 执行纪律

- read_file/edit_file/grep/search_files 读代码，禁止 run_python 读文件
- 写完代码必须跑测试确认
- 改 API 签名必须 grep 搜索所有引用
- 每个任务完成后给一句结论，不啰嗦

## 环境

- Windows 11，Git Bash 可用，在 {provider_name} 连接下工作"""


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


def reset_prompt_cache() -> None:
    """Reset the global prompt cache (for test isolation)."""
    global _cache, _COLD_LORE_LOADED
    _cache = PromptCache()
    _COLD_LORE_LOADED = {}


# ── 谱系注入注册表（每项: (模块路径, 函数名, 描述)）───
# CHAT mode: 7 useful layers (trimmed from 17 decorative spectrum layers)
# 仅当 chat_light=False 时使用（当前无调用方走此路径）
_SPECTRUM_INJECTIONS: list[tuple[str, str, str]] = [
    ("core.marketplace", "get_marketplace", "技能市场"),
]

# 轻量聊天注入：marketplace + rules（核心规则在所有模式生效）
_CHAT_LIGHT_INJECTIONS: list[tuple[str, str, str]] = [
    ("core.marketplace", "get_marketplace", "技能市场"),
    ("core.rules", "get_rules", "rules injection"),
]

_CODE_SPECTRUM_INJECTIONS: list[tuple[str, str, str]] = [
    # marketplace 已从 CODE 模式移除 — 编码时不需要技能市场状态（省 ~233 tokens/请求）
    ("core.rules", "get_rules", "rules injection"),
]

# 热路径身份注入 — 极简一行，不加载七兽/金手指世界观
_HOT_IDENTITY = "CRUX Studio v6.1.0 — 平时如刀，出事成阵 · Multi-Agent 已模块化"

# 冷路径叙事 — 按需加载，不自动注入
# (Previously held golden_finger + seven_beasts_fusion — both deleted as dead code.
#  The cold-lore infrastructure remains intact for future use.)
_COLD_LORE: dict[str, tuple[str, str, str]] = {}

_COLD_LORE_LOADED: dict[str, str] = {}  # 缓存


def load_cold_lore(name: str) -> str:
    """按需加载冷路径叙事。仅当用户问起或系统诊断时调用。"""
    if name in _COLD_LORE_LOADED:
        return _COLD_LORE_LOADED[name]
    if name not in _COLD_LORE:
        return ""
    mod_path, func_name, _ = _COLD_LORE[name]
    try:
        import importlib

        mod = importlib.import_module(mod_path)
        fn = getattr(mod, func_name, None)
        if fn is not None:
            result = fn()
            if isinstance(result, str):
                _COLD_LORE_LOADED[name] = result
                return result
    except Exception as _es:
        catch(_es, "core.chat_prompt", "swallowed")
    return ""


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
    # 热路径注入文件
    for mod_path, _, _ in _SPECTRUM_INJECTIONS + _CODE_SPECTRUM_INJECTIONS + _CHAT_LIGHT_INJECTIONS:
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
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
    # 冷路径叙事文件（也会影响缓存：内容变了就要重建）
    for mod_path, _, _ in _COLD_LORE.values():
        if mod_path in seen:
            continue
        seen.add(mod_path)
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            f = getattr(mod, "__file__", None)
            if f:
                mtimes.append(str(int(os.path.getmtime(f))))
        except Exception as _es:
            catch(_es, "core.chat_prompt", "swallowed")
    # 兜底：lore 目录下所有 .py（含新增/重命名文件）
    lore_dir = os.path.join(os.path.dirname(__file__), "lore")
    if os.path.isdir(lore_dir):
        for f in sorted(os.listdir(lore_dir)):
            if f.endswith(".py"):
                mtimes.append(str(int(os.path.getmtime(os.path.join(lore_dir, f)))))
    if not mtimes:
        return ""
    return hashlib.md5("|".join(mtimes).encode(), usedforsecurity=False).hexdigest()[:12]


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
    chat_light: bool = True,
) -> str:
    """构建完整 system prompt — ChatSession 的独立调用入口。

    Args:
        model: 当前模型 ID
        provider_name: 供应商人类可读名
        code_mode: 是否为代码模式（自动跳过 chat_light）
        browser_enabled: Browser Companion 已启用
        notebook_enabled: Notebook 工具已启用
        audio_enabled: 音频工具已启用
        active_skill_rules_hash: 当前活跃规则的 hash（纳入缓存 key）
        skills_auto_prompt_manager: SkillManager 实例（用于 auto_skills_prompt）
        chat_light: 轻量聊天模式，跳过 Claude DNA + Rules 编码方法论（省 ~1200 tokens）

    Returns:
        完整的系统提示词字符串。
    """
    template = CODE_SYSTEM_PROMPT if code_mode else CHAT_SYSTEM_PROMPT
    cache_key = (
        f"{provider_name}|{model}|{code_mode}|L{chat_light}"
        f"|b{browser_enabled}|n{notebook_enabled}|a{audio_enabled}"
        f"|{active_skill_rules_hash}"
        f"|{_get_injections_fingerprint()}"
    )

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    base = template.format(provider_name=provider_name, model_name=model)
    # ── Workspace context: tell the LLM which project it operates on ──

    from core.workspace_guard import get_crux_root, resolve_workspace

    _ws = str(resolve_workspace())
    _crux_root = str(get_crux_root())
    base += f"\n\n## 工作目录\n项目路径: `{_ws}`\nCRUX 安装路径: `{_crux_root}`\n"
    # ── 项目记忆：从 workspace 加载 .crux/context.md（如存在）──
    _ws_path = Path(_ws)
    for _fname, _label in ((".crux/context.md", "项目记忆"), (".crux_identity.md", "项目身份")):
        _mem_file = _ws_path / _fname
        if _mem_file.exists():
            try:
                _mem_text = _mem_file.read_text(encoding="utf-8").strip()
                if _mem_text:
                    base += f"\n\n## {_label}\n{_mem_text}"
            except (OSError, UnicodeDecodeError):
                pass  # 静默失败，不影响启动

    # ── 热路径身份：一行极简，不做世界观注入 ──
    base += "\n\n" + _HOT_IDENTITY

    # 谱系注入：CODE 模式注全部方法论，CHAT_LIGHT 只注 marketplace
    if code_mode:
        injections = _CODE_SPECTRUM_INJECTIONS
    elif chat_light:
        injections = _CHAT_LIGHT_INJECTIONS
    else:
        injections = _SPECTRUM_INJECTIONS
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
            elif func_name == "get_marketplace" or func_name == "get_orchestra":
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
            "所有输出保存到 output/audio/。补齐视频项目旁白+BGM 音轨。"
        )

    # Skill 三态：注入所有 trigger=auto 的技能 prompt
    if skills_auto_prompt_manager is not None:
        base = skills_auto_prompt_manager(base)

    # 存入缓存
    _cache.set(cache_key, base)
    return base
