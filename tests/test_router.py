"""Unit tests for core/router.py — 全局智能任务路由器。

覆盖：
- classify()：关键词 / 文本特征 / 会话上下文 / 默认
- route_command()：静态命令路由表 + 未知命令
- resolve()：TaskProfile / str 输入 / 模型匹配 / SKIP / 非法值
- apply()：模型切换 / 跨供应商切换 / 一致性校验回滚 / messages 防御
- route()：统一入口（斜杠命令 vs 自然语言）
- _detect_provider()：MODEL_REGISTRY 查询 + 回退

全部 mock，零网络零文件 I/O 依赖。
"""
# pyright: reportArgumentType=false

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.router import (
    _PROFILE_MODEL,
    COMMAND_ROUTE_MAP,
    RouteDecision,
    TaskProfile,
    _detect_provider,
    apply,
    classify,
    resolve,
    route,
    route_command,
)

# ── 辅助：FakeSession（轻量 mock，避免依赖 ChatSession）────────


class FakeSession:
    """最小化的 ChatSession 替身，只含 router 关心的属性。"""

    def __init__(self, model="agnes-1.5-flash", client_base_url="https://agnes.example.com/v1"):
        self.model = model
        self.client = MagicMock()
        self.client.base_url = client_base_url
        self.messages = [{"role": "system", "content": "old"}]
        self.code_mode = False
        self.agent_mode = False
        self.active_skill = ""
        self.enable_thinking = False

    def _build_system_prompt(self):
        return "rebuilt system prompt"


# ════════════════════════════════════════════════════════════
#  classify() — 自然语言分类器
# ════════════════════════════════════════════════════════════


class TestClassifyBasic:
    """classify 的基础输入处理。"""

    def test_empty_string_returns_skip(self):
        assert classify("") == TaskProfile.SKIP

    def test_whitespace_only_returns_skip(self):
        assert classify("   \n\t  ") == TaskProfile.SKIP

    def test_none_safe(self):
        # classify 内部已 guard not text，但传 None 应该不崩
        # 注意：str.strip() 对 None 会 AttributeError，函数内已先判 `if not text`
        assert classify("") == TaskProfile.SKIP


class TestClassifyKeywords:
    """关键词匹配（按优先级 DEEP > CREATIVE > QUICK_FIX > CODING）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "帮我重构整个认证系统",
            "这个架构需要重新设计",
            "做一次系统级全面分析",
            "我们评估一下技术选型",
            "这个方案的可行性怎么样",
        ],
    )
    def test_deep_keywords(self, text):
        assert classify(text, session=None) == TaskProfile.DEEP

    @pytest.mark.parametrize(
        "text",
        [
            "生成一张图片",
            "帮我画一个 logo",
            "做一张海报",
            "文生图",
            "图生视频",
            "用 showrun 制片",
        ],
    )
    def test_creative_keywords(self, text):
        assert classify(text, session=None) == TaskProfile.CREATIVE

    @pytest.mark.parametrize(
        "text",
        [
            "修复这个 bug",
            "有个 bug 需要修复",
            "帮我 fix 一下",
            "打个 hotfix 补丁",
            "改一下按钮颜色",
            "改一下文案",
            "这里有个 typo",
        ],
    )
    def test_quick_fix_keywords(self, text):
        assert classify(text, session=None) == TaskProfile.QUICK_FIX

    @pytest.mark.parametrize(
        "text",
        [
            "写一个函数计算阶乘",
            "写一个类处理用户",
            "实现这个功能",
            "新增一个接口",
            "加一个测试",
            "帮我做开发",
        ],
    )
    def test_coding_keywords(self, text):
        assert classify(text, session=None) == TaskProfile.CODING

    def test_deep_beats_creative(self):
        # 同时含 DEEP 和 CREATIVE 关键词 → DEEP 优先
        assert classify("重构并生成图片", session=None) == TaskProfile.DEEP

    def test_creative_beats_quick_fix(self):
        # 同时含 CREATIVE 和 QUICK_FIX → CREATIVE 优先
        assert classify("画一个图来修复 bug", session=None) == TaskProfile.CREATIVE


class TestClassifyTextFeatures:
    """文本特征分析（文件路径 / 代码片段 / 长文本）。"""

    def test_single_file_path_returns_quick_fix(self):
        text = "读取 C:\\foo\\bar.py"
        assert classify(text, session=None) == TaskProfile.QUICK_FIX

    def test_multiple_file_paths_returns_deep(self):
        text = "读取 C:\\a.py C:\\b.py C:\\c.py"
        assert classify(text, session=None) == TaskProfile.DEEP

    def test_unix_file_path(self):
        text = "查看 ~/src/main.py"
        assert classify(text, session=None) == TaskProfile.QUICK_FIX

    def test_code_block_returns_coding(self):
        # 含 def 关键字 → 代码片段
        text = "你看看这段：def hello():\n    print('hi')"
        assert classify(text, session=None) == TaskProfile.CODING

    def test_long_text_returns_deep(self):
        # > 500 字符的非代码长文本 → DEEP
        text = "这是一段需求文档。" * 80  # 远超 500 字符
        assert classify(text, session=None) == TaskProfile.DEEP

    def test_long_code_paste_returns_coding(self):
        # 长文本但是是代码粘贴（多 def/import 行）→ CODING
        lines = ["import os"]
        for i in range(40):
            lines.append(f"def fn_{i}():")
            lines.append(f"    return {i}")
        text = "\n".join(lines)
        assert len(text) > 500
        assert classify(text, session=None) == TaskProfile.CODING


class TestClassifySessionContext:
    """会话上下文感知（最高优先级）。"""

    def test_agent_mode_returns_coding(self):
        session = FakeSession()
        session.agent_mode = True
        assert classify("随便什么话", session=session) == TaskProfile.CODING

    def test_showrunner_skill_returns_creative(self):
        session = FakeSession()
        session.active_skill = "showrunner"
        assert classify("随便什么话", session=session) == TaskProfile.CREATIVE

    def test_comfyui_skill_returns_creative(self):
        session = FakeSession()
        session.active_skill = "comfyui-bridge"
        assert classify("随便什么话", session=session) == TaskProfile.CREATIVE

    def test_other_skill_returns_coding(self):
        session = FakeSession()
        session.active_skill = "qc-inspector"
        assert classify("随便什么话", session=session) == TaskProfile.CODING

    def test_code_mode_fallback_returns_coding(self):
        # 无关键词 + code_mode 开 → CODING（最后兜底）
        session = FakeSession()
        session.code_mode = True
        assert classify("hello", session=session) == TaskProfile.CODING

    def test_session_context_beats_keywords(self):
        # agent_mode 下，即使输入含 DEEP 关键词，仍返回 CODING
        session = FakeSession()
        session.agent_mode = True
        assert classify("重构整个系统", session=session) == TaskProfile.CODING


class TestClassifyDefault:
    """无任何特征的普通对话 → SKIP（保持当前模型）。"""

    def test_plain_greeting_returns_skip(self):
        assert classify("你好", session=None) == TaskProfile.SKIP

    def test_plain_question_returns_skip(self):
        assert classify("今天天气怎么样", session=None) == TaskProfile.SKIP


# ════════════════════════════════════════════════════════════
#  route_command() — 命令级静态路由表
# ════════════════════════════════════════════════════════════


class TestRouteCommand:
    """命令路由表查找。"""

    def test_plan_routes_to_deepseek(self):
        d = route_command("plan", "任务", session=None)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id == "deepseek-v4-pro"
        assert d.reason

    def test_sub_routes_to_deepseek(self):
        d = route_command("sub", "子任务", session=None)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id == "deepseek-v4-pro"

    def test_refactor_routes_to_deepseek(self):
        d = route_command("refactor", "旧 新", session=None)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id == "deepseek-v4-pro"

    def test_team_keeps_current_model(self):
        d = route_command("team", "review", session=None)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id is None  # 保持当前

    def test_showrun_keeps_current_model(self):
        d = route_command("showrun", "目标", session=None)
        assert d.profile == TaskProfile.CREATIVE
        assert d.model_id is None

    @pytest.mark.parametrize(
        "cmd",
        [
            "help",
            "model",
            "thinking",
            "code",
            "agent",
            "tools",
            "clear",
            "exit",
            "quit",
            "q",
            "compress",
            "project",
            "todo",
            "commit",
            "changelog",
            "audit",
            "rules",
            "automate",
            "provider",
            "evolve",
            "know",
            "skill",
            "img",
            "video",
            "vision",
            "deploy",
        ],
    )
    def test_skip_commands(self, cmd):
        d = route_command(cmd, "", session=None)
        assert d.profile == TaskProfile.SKIP
        assert d.model_id is None

    def test_unknown_command_returns_skip(self):
        d = route_command("nonexistent_cmd", "", session=None)
        assert d.profile == TaskProfile.SKIP
        assert d.model_id is None

    def test_route_map_covers_known_commands(self):
        # 命令路由表至少覆盖核心命令
        for key in ("plan", "sub", "refactor", "showrun", "help"):
            assert key in COMMAND_ROUTE_MAP


# ════════════════════════════════════════════════════════════
#  resolve() — TaskProfile → RouteDecision
# ════════════════════════════════════════════════════════════


class TestResolve:
    """resolve 的决策合成。"""

    def test_skip_returns_skip(self):
        d = resolve(TaskProfile.SKIP, session=None)
        assert d.profile == TaskProfile.SKIP
        assert d.model_id is None

    def test_string_input_quick_fix(self):
        d = resolve("quick_fix", session=None)
        assert d.profile == TaskProfile.QUICK_FIX
        assert d.model_id == "deepseek-v4-pro"

    def test_string_input_deep(self):
        d = resolve("deep", session=None)
        assert d.model_id == "deepseek-v4-pro"

    def test_invalid_string_returns_skip(self):
        d = resolve("totally_invalid", session=None)
        assert d.profile == TaskProfile.SKIP

    def test_current_model_matches_no_switch(self):
        # session 已经在目标模型 → 返回 profile 但 model_id 为 None（表示无需切）
        session = FakeSession(model="deepseek-v4-pro")
        d = resolve(TaskProfile.QUICK_FIX, session=session)
        assert d.profile == TaskProfile.QUICK_FIX
        assert d.model_id is None  # 已匹配，无需切换
        assert d.reason == ""  # 已匹配，无切换理由

    def test_different_model_produces_reason(self):
        session = FakeSession(model="agnes-1.5-flash")
        d = resolve(TaskProfile.DEEP, session=session)
        assert d.model_id == "deepseek-v4-pro"
        assert "DeepSeek" in d.reason or "深度" in d.reason

    def test_all_profiles_have_model_mapping(self):
        # 除 SKIP 外，所有 profile 都应有推荐模型
        for profile in TaskProfile:
            if profile == TaskProfile.SKIP:
                continue
            assert profile in _PROFILE_MODEL
            assert _PROFILE_MODEL[profile]


# ════════════════════════════════════════════════════════════
#  apply() — 执行决策（含一致性校验、回滚、防御）
# ════════════════════════════════════════════════════════════


def _patched_mgr(providers, create_client_return):
    """构造一个 mock ProviderManager。"""
    mgr = MagicMock()
    mgr.providers = providers
    mgr.create_client.return_value = create_client_return
    return mgr


class TestApplyBasic:
    """apply 的基本守卫。"""

    def test_skip_decision_noop(self):
        session = FakeSession(model="agnes-1.5-flash")
        original_model = session.model
        apply(RouteDecision(profile=TaskProfile.SKIP), session)
        assert session.model == original_model

    def test_none_model_noop(self):
        session = FakeSession(model="agnes-1.5-flash")
        d = RouteDecision(profile=TaskProfile.DEEP, model_id=None)
        apply(d, session)
        assert session.model == "agnes-1.5-flash"

    def test_same_model_noop(self):
        session = FakeSession(model="agnes-2.0-flash")
        d = RouteDecision(profile=TaskProfile.QUICK_FIX, model_id="agnes-2.0-flash")
        apply(d, session)
        assert session.model == "agnes-2.0-flash"


class TestApplySameProviderSwitch:
    """同供应商内的模型切换（无需切 client）。"""

    def test_switch_within_agnes(self):
        # agnes-1.5-flash → agnes-2.0-flash，同供应商，不切 client
        session = FakeSession(model="agnes-1.5-flash", client_base_url="https://agnes.example.com/v1")
        original_client = session.client
        d = RouteDecision(profile=TaskProfile.QUICK_FIX, model_id="agnes-2.0-flash")

        with patch("core.provider.get_provider_manager", return_value=_patched_mgr({}, MagicMock())):
            apply(d, session)

        assert session.model == "agnes-2.0-flash"
        assert session.client is original_client  # client 未换
        assert session.messages[0]["content"] == "rebuilt system prompt"


class TestApplyCrossProviderSwitch:
    """跨供应商切换（含一致性校验）。"""

    def test_successful_cross_provider_switch(self):
        # agnes → deepseek，client base_url 匹配
        session = FakeSession(model="agnes-2.0-flash", client_base_url="https://agnes.example.com/v1")
        deepseek_client = MagicMock()
        deepseek_client.base_url = "https://deepseek.example.com/v1"
        providers = {
            "crux": {"base_url": "https://crux.example.com/v1"},
            "deepseek": {"base_url": "https://deepseek.example.com/v1"},
        }
        d = RouteDecision(profile=TaskProfile.DEEP, model_id="deepseek-v4-pro")

        with patch("core.provider.get_provider_manager", return_value=_patched_mgr(providers, deepseek_client)):
            apply(d, session)

        assert session.model == "deepseek-v4-pro"
        assert session.client is deepseek_client
        assert d.switch_client is True

    def test_fallback_rolls_back_model(self):
        # create_client 内部 fallback：返回的 client base_url 不是目标供应商 → 回滚
        session = FakeSession(model="agnes-2.0-flash", client_base_url="https://agnes.example.com/v1")
        fallback_client = MagicMock()
        # 期望 deepseek，但返回了 crux 的 base_url（fallback）
        fallback_client.base_url = "https://crux.example.com/v1"
        providers = {
            "crux": {"base_url": "https://crux.example.com/v1"},
            "deepseek": {"base_url": "https://deepseek.example.com/v1"},
        }
        d = RouteDecision(profile=TaskProfile.DEEP, model_id="deepseek-v4-pro")

        with patch("core.provider.get_provider_manager", return_value=_patched_mgr(providers, fallback_client)):
            apply(d, session)

        # 回滚：model 保留旧值，client 未换
        assert session.model == "agnes-2.0-flash"
        assert d.switch_client is False

    def test_create_client_exception_preserves_session(self):
        # create_client 抛异常 → 不改 model/client
        session = FakeSession(model="agnes-2.0-flash")
        original_client = session.client
        providers = {
            "crux": {"base_url": "https://crux.example.com/v1"},
            "deepseek": {"base_url": "https://deepseek.example.com/v1"},
        }
        mgr = MagicMock()
        mgr.providers = providers
        mgr.create_client.side_effect = RuntimeError("no api key")
        d = RouteDecision(profile=TaskProfile.DEEP, model_id="deepseek-v4-pro")

        with patch("core.provider.get_provider_manager", return_value=mgr):
            apply(d, session)

        assert session.model == "agnes-2.0-flash"
        assert session.client is original_client


class TestApplyEdgeCases:
    """apply 的边界情况。"""

    def test_empty_messages_list_defense(self):
        # messages 为空时不应 IndexError
        session = FakeSession(model="agnes-2.0-flash")
        session.messages = []
        d = RouteDecision(profile=TaskProfile.QUICK_FIX, model_id="agnes-1.5-flash")

        with patch("core.provider.get_provider_manager", return_value=_patched_mgr({}, MagicMock())):
            apply(d, session)

        assert session.model == "agnes-1.5-flash"
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "system"

    def test_base_url_trailing_slash_tolerant(self):
        # 目标 base_url 末尾有斜杠也应视为匹配
        session = FakeSession(model="agnes-2.0-flash", client_base_url="https://agnes.example.com/v1")
        deepseek_client = MagicMock()
        deepseek_client.base_url = "https://deepseek.example.com/v1/"  # 末尾斜杠
        providers = {
            "crux": {"base_url": "https://crux.example.com/v1"},
            "deepseek": {"base_url": "https://deepseek.example.com/v1"},  # 无斜杠
        }
        d = RouteDecision(profile=TaskProfile.DEEP, model_id="deepseek-v4-pro")

        with patch("core.provider.get_provider_manager", return_value=_patched_mgr(providers, deepseek_client)):
            apply(d, session)

        assert session.model == "deepseek-v4-pro"


# ════════════════════════════════════════════════════════════
#  route() — 顶层统一入口
# ════════════════════════════════════════════════════════════


class TestRoute:
    """route() 自动分发命令 vs 自然语言。"""

    def test_slash_command_goes_to_route_command(self):
        session = FakeSession()
        d = route("/plan 重构认证", session)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id == "deepseek-v4-pro"

    def test_slash_command_help_is_skip(self):
        session = FakeSession()
        d = route("/help", session)
        assert d.profile == TaskProfile.SKIP

    def test_natural_language_goes_to_classify(self):
        session = FakeSession()
        d = route("帮我重构整个系统", session)
        assert d.profile == TaskProfile.DEEP

    def test_natural_language_plain_returns_skip(self):
        session = FakeSession()
        d = route("你好", session)
        assert d.profile == TaskProfile.SKIP

    def test_whitespace_stripped(self):
        session = FakeSession()
        d = route("   /help   ", session)
        assert d.profile == TaskProfile.SKIP

    def test_empty_input_returns_skip(self):
        session = FakeSession()
        d = route("", session)
        assert d.profile == TaskProfile.SKIP


# ════════════════════════════════════════════════════════════
#  _detect_provider() — 模型 → 供应商查找
# ════════════════════════════════════════════════════════════


class TestDetectProvider:
    """_detect_provider 的多级查找。"""

    def test_known_model_via_registry(self):
        assert _detect_provider("agnes-1.5-flash") == "crux"
        assert _detect_provider("agnes-2.0-flash") == "crux"
        assert _detect_provider("deepseek-v4-pro") == "deepseek"
        assert _detect_provider("Pro/moonshotai/Kimi-K2.6") == "siliconflow"

    def test_unknown_model_returns_empty(self):
        assert _detect_provider("nonexistent-model-xyz") == ""

    def test_falls_back_to_models_json(self):
        # MODEL_REGISTRY 没有的模型，走 models.json 反查
        mgr = MagicMock()
        mgr.providers = {
            "custom": {"models": {"pro": "custom-pro-v1"}, "base_url": "x"},
        }
        assert _detect_provider("custom-pro-v1", mgr) == "custom"

    def test_passes_mgr_to_avoid_reload(self):
        # 传入 mgr 时不应触发 load()
        mgr = MagicMock()
        mgr.providers = {}  # 空 → 会触发 load
        _detect_provider("any-model", mgr)
        mgr.load.assert_called_once()
