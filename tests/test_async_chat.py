"""Unit tests for AsyncChatSession — session state, tool dispatch, and streaming.

Tests the async counterpart of ChatSession without hitting real APIs,
using MagicMock for AsyncAgnesClient and async generators for stream mocks.

风格对齐：与 tests/test_async_render.py 一致，所有 async 测试都用**同步测试
方法 + asyncio.run()**运行。asyncio.run 每次新建+关闭独立 event loop，不受
@pytest.mark.asyncio 测试（如 test_async_executor）在 teardown 时清空全局 loop
的污染——这正是 get_event_loop().run_until_complete() 在跨文件运行时崩溃的根因。
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.async_chat import AsyncChatSession


# ── Helpers ────────────────────────────────────────────────

def _run(coro):
    """同步运行 async 协程。

    用 asyncio.run 而非 get_event_loop().run_until_complete：
    pytest-asyncio 的 @pytest.mark.asyncio 测试在 teardown 时会清空当前线程的
    event loop（asyncio.set_event_loop(None)），导致后续 get_event_loop() 抛
    RuntimeError 'There is no current event loop'。asyncio.run 每次新建+关闭
    loop，不受全局 loop 状态污染。
    """
    return asyncio.run(coro)


def make_mock_client():
    """创建 mock AsyncAgnesClient（chat_stream 返回空 async iter）。"""
    client = MagicMock(spec=["chat_stream", "chat", "chat_multimodal"])
    # chat_stream 是 async generator 函数调用 → 返回 async generator 对象
    client.chat_stream = lambda *a, **kw: _empty_async_iter()
    client.chat = AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}]})
    client.chat_multimodal = AsyncMock(return_value={
        "choices": [{"message": {"content": "描述：一只猫"}}]
    })
    return client


async def _empty_async_iter():
    """返回空的 async iterator（无 yield）。"""
    return
    yield  # 让函数成为 async generator


async def _async_iter_items(*items):
    """返回包含指定 items 的 async iterator。"""
    for item in items:
        yield item


def async_iter_of(*items):
    """工厂函数：返回一个可调用，调用时返回包含 items 的 async generator。"""
    def _make(*a, **kw):
        return _async_iter_items(*items)
    return _make


def make_session(client=None):
    """创建 AsyncChatSession（mock 所有依赖）。"""
    if client is None:
        client = make_mock_client()
    return AsyncChatSession(client)


async def _collect(agen):
    """消费 async generator，返回 [(kind, payload), ...] 列表。"""
    out = []
    async for item in agen:
        out.append(item)
    return out


# ── Test: Construction & State ─────────────────────────────

class TestAsyncChatSessionInit:
    """测试 AsyncChatSession 初始化和状态。"""

    def test_init_has_system_message(self):
        session = make_session()
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "system"
        assert "agnes-1.5-flash" in session.messages[0]["content"]

    def test_init_default_model(self):
        session = make_session()
        assert session.model == "agnes-1.5-flash"

    def test_init_custom_model(self):
        client = make_mock_client()
        session = AsyncChatSession(client, default_model="deepseek-v4-pro")
        assert session.model == "deepseek-v4-pro"

    def test_init_code_mode_off(self):
        session = make_session()
        assert session.code_mode is False
        assert session.agent_mode is False

    def test_init_has_tools_registry(self):
        session = make_session()
        assert session.tools is not None

    def test_vision_client_defaults_to_main(self):
        client = make_mock_client()
        session = AsyncChatSession(client)
        assert session.vision_client is client


# ── Test: Toggle Modes ─────────────────────────────────────

class TestAsyncChatSessionToggle:
    """测试模式切换。"""

    def test_toggle_code_mode(self):
        session = make_session()
        result = session.toggle_code_mode()
        assert result is True
        assert session.code_mode is True
        assert session.enable_thinking is True

    def test_toggle_code_mode_back(self):
        session = make_session()
        session.toggle_code_mode()
        result = session.toggle_code_mode()
        assert result is False
        assert session.code_mode is False

    def test_toggle_code_mode_clears_history(self):
        session = make_session()
        session.messages.append({"role": "user", "content": "hello"})
        session.toggle_code_mode()
        assert len(session.messages) == 1

    def test_reset_clears_history(self):
        session = make_session()
        session.messages.append({"role": "user", "content": "hello"})
        session.reset()
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "system"


# ── Test: Vision Fallback ────────────────────────────────

class TestAsyncVisionFallback:
    """测试视觉理解 fallback 链（async）。"""

    def test_vision_fallback_first_model_succeeds(self):
        client = make_mock_client()
        client.chat_multimodal = AsyncMock(return_value={
            "choices": [{"message": {"content": "一只橘猫坐在沙发上"}}]
        })
        session = AsyncChatSession(client)
        result = _run(session._vision_fallback("描述这张图", "http://example.com/cat.jpg"))
        assert "橘猫" in result

    def test_vision_fallback_falls_to_next_model(self):
        """第一个模型失败，fallback 到第二个。"""
        client = make_mock_client()
        call_count = 0

        async def _mock_multimodal(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("timeout")
            return {"choices": [{"message": {"content": "沙漠风景"}}]}

        client.chat_multimodal = _mock_multimodal
        session = AsyncChatSession(client, vision_model="model-a")
        # Patch chain to have 2 models so fallback can occur
        with patch("core.async_chat.get_vision_models", return_value=["model-b"]):
            result = _run(session._vision_fallback("描述", "http://example.com/desert.jpg"))
        assert "沙漠风景" in result
        assert call_count >= 2

    def test_vision_fallback_all_fail(self):
        """所有模型都失败时返回错误信息。"""
        client = make_mock_client()
        client.chat_multimodal = AsyncMock(side_effect=OSError("network down"))
        session = AsyncChatSession(client)
        result = _run(session._vision_fallback("描述", "http://example.com/x.jpg"))
        assert "视觉理解失败" in result


# ── Test: Tool Dispatch ──────────────────────────────────

class TestAsyncDispatchTool:
    """测试 async _dispatch_tool。"""

    def test_unknown_tool(self):
        session = make_session()
        text, effects = _run(session._dispatch_tool("nonexistent_tool", "{}"))
        assert "未知工具" in text
        assert effects == []

    def test_high_risk_tool_returns_confirm(self):
        session = make_session()
        text, effects = _run(session._dispatch_tool("git_push", '{"branch":"main"}'))
        assert text == ""
        assert len(effects) == 1
        assert effects[0][0] == "confirm"
        assert effects[0][1]["tool"] == "git_push"

    def test_high_risk_bash_with_delete(self):
        session = make_session()
        text, effects = _run(session._dispatch_tool(
            "run_bash", '{"command":"rm -rf /tmp/stuff"}'
        ))
        assert text == ""
        assert effects[0][0] == "confirm"

    def test_generate_image_tool(self):
        """generate_image 调用 brain enhance + t2i.generate。"""
        client = make_mock_client()
        session = AsyncChatSession(client)
        session.brain.enhance_image_prompt = AsyncMock(return_value={
            "optimized_prompt": "optimized: cat",
            "negative_prompt": "blurry",
        })
        session.t2i.generate = AsyncMock(return_value={
            "local_path": "/tmp/cat.png",
            "url": "http://example.com/cat.png",
        })
        text, effects = _run(session._dispatch_tool(
            "generate_image", '{"prompt":"一只猫"}'
        ))
        assert "已生成" in text
        kinds = [e[0] for e in effects]
        assert "info" in kinds
        assert "image" in kinds

    def test_generate_video_tool(self):
        """generate_video 调用 brain enhance + vid.text_to_video。"""
        client = make_mock_client()
        session = AsyncChatSession(client)
        session.brain.enhance_video_prompt = AsyncMock(return_value={
            "optimized_prompt": "optimized: ocean waves",
            "negative_prompt": "static",
        })
        session.vid.text_to_video = AsyncMock(return_value={
            "local_path": "/tmp/video.mp4",
            "video_id": "vid_123",
            "status": "completed",
        })
        text, effects = _run(session._dispatch_tool(
            "generate_video", '{"prompt":"海浪拍打"}'
        ))
        assert "已生成" in text
        kinds = [e[0] for e in effects]
        assert "video" in kinds

    def test_external_tool_via_registry(self):
        """外部工具通过 ToolRegistry.execute（asyncio.to_thread）执行。"""
        client = make_mock_client()
        session = AsyncChatSession(client)
        session.tools.register("test_echo", "echo tool", {}, lambda **kw: kw.get("msg", "echo"))
        text, effects = _run(session._dispatch_tool(
            "test_echo", '{"msg":"hello world"}'
        ))
        assert "hello world" in text
        kinds = [e[0] for e in effects]
        assert "info" in kinds


# ── Test: send_stream (pure text) ──────────────────────────

class TestAsyncSendStream:
    """测试 async send_stream 核心流程。"""

    def test_pure_text_yields_text(self):
        """纯文本消息：流式 yield text chunks。"""
        client = make_mock_client()
        deltas = [
            {"content": "你"},
            {"content": "好"},
            {"content": "！"},
            {"_finish": "stop"},
        ]
        client.chat_stream = async_iter_of(*deltas)
        session = AsyncChatSession(client)
        session.model = "agnes-1.5-flash"  # 非 tool-calling 模型

        collected = _run(_collect(session.send_stream("你好")))

        texts = [p for k, p in collected if k == "text"]
        assert "".join(texts) == "你好！"
        # 应有 assistant message
        assert len(session.messages) == 3  # system + user + assistant

    def test_multimodal_calls_vision(self):
        """带图片的消息：走 vision_client。"""
        client = make_mock_client()
        client.chat_multimodal = AsyncMock(return_value={
            "choices": [{"message": {"content": "这是日落照片"}}]
        })
        session = AsyncChatSession(client)
        session.model = "agnes-1.5-flash"

        collected = _run(_collect(session.send_stream(
            "描述", image_url="http://example.com/sunset.jpg"
        )))

        assert len(collected) >= 1
        assert collected[0][0] == "text"
        assert "日落" in collected[0][1]
        client.chat_multimodal.assert_called_once()

    def test_tool_call_dispatch(self):
        """工具调用：流式累积 → merge → dispatch → 结果喂回 → 二次流式。"""
        client = make_mock_client()

        # 第一轮流式：有 tool_call
        round1_deltas = [
            {"content": "我来帮你生成图片"},
            {"tool_calls": [{"index": 0, "id": "call_1",
                             "function": {"name": "generate_image",
                                          "arguments": '{"prompt":"星空"}'}}]},
            {"_finish": "tool_calls"},
        ]
        # 第二轮流式：模型总结
        round2_deltas = [
            {"content": "图片已生成完毕，"},
            {"content": "展现璀璨星空。"},
            {"_finish": "stop"},
        ]

        stream_seq = [round1_deltas, round2_deltas]
        stream_idx = 0

        def _mock_stream(*a, **kw):
            nonlocal stream_idx
            result = stream_seq[stream_idx]
            stream_idx += 1
            return _async_iter_items(*result)

        client.chat_stream = _mock_stream
        session = AsyncChatSession(client)
        session.brain.enhance_image_prompt = AsyncMock(return_value={
            "optimized_prompt": "star sky", "negative_prompt": None,
        })
        session.t2i.generate = AsyncMock(return_value={
            "local_path": "/tmp/star.png", "url": "http://x/star.png",
        })
        # 确保 supports_tools 为 True
        with patch("core.async_chat.model_supports_tools", return_value=True):
            collected = _run(_collect(session.send_stream("帮我画星空")))

        # 验证收到了文本 + 副作用（info + image）+ 二次流式文本
        kinds = [k for k, _ in collected]
        assert "text" in kinds
        assert "image" in kinds
        # 验证 messages 中包含 tool result
        roles = [m["role"] for m in session.messages]
        assert "tool" in roles

    def test_max_tool_loops_stop(self):
        """超出最大工具调用轮次时优雅停止。"""
        client = make_mock_client()

        # 每轮都返回 tool_call，迫使循环持续
        async def _infinite_tool_stream(*a, **kw):
            yield {"content": "思考中"}
            yield {"tool_calls": [{"index": 0, "id": "call_x",
                                   "function": {"name": "generate_image",
                                                "arguments": '{"prompt":"x"}'}}]}
            yield {"_finish": "tool_calls"}

        client.chat_stream = _infinite_tool_stream
        session = AsyncChatSession(client)
        session.brain.enhance_image_prompt = AsyncMock(return_value={
            "optimized_prompt": "x", "negative_prompt": None,
        })
        session.t2i.generate = AsyncMock(return_value={
            "local_path": "/tmp/x.png",
        })
        # 缩小最大轮次以便测试
        with patch("core.async_chat.MAX_TOOL_LOOPS", 2):
            with patch("core.async_chat.model_supports_tools", return_value=True):
                collected = _run(_collect(session.send_stream("无限循环")))
                # 应该有 "已达到最大" 的 info
                info_msgs = [p for k, p in collected if k == "info"]
                assert any("已达到最大工具调用轮次" in msg for msg in info_msgs)


# ── Test: Cross-round Dedup ────────────────────────────────

class TestAsyncCrossRoundDedup:
    """测试跨轮工具去重。"""

    def test_readonly_tool_dedup(self):
        """只读工具在跨轮中不重复执行。"""
        call_count = 0

        async def _mock_stream(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"content": ""}
                yield {"tool_calls": [{"index": 0, "id": "call_1",
                                       "function": {"name": "web_search",
                                                    "arguments": '{"query":"python"}'}}]}
                yield {"_finish": "tool_calls"}
            else:
                yield {"content": "结果已获取"}
                yield {"_finish": "stop"}

        client = make_mock_client()
        client.chat_stream = _mock_stream
        session = AsyncChatSession(client)
        # 注册一个 web_search mock
        session.tools.register("web_search", "search", {}, lambda **kw: "result: python")

        with patch("core.async_chat.model_supports_tools", return_value=True):
            collected = _run(_collect(session.send_stream("搜索python")))

        # 验证 messages 结构正确
        tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
        assert len(tool_msgs) >= 1


# ── Test: Session State Management ─────────────────────────

class TestAsyncSessionState:
    """测试会话状态管理。"""

    def test_messages_accumulate(self):
        """多轮对话 messages 正确累积。"""
        client = make_mock_client()
        deltas = [{"content": "回复A"}, {"_finish": "stop"}]
        client.chat_stream = async_iter_of(*deltas)
        session = AsyncChatSession(client)

        _run(_collect(session.send_stream("第一轮")))
        assert len(session.messages) == 3  # system + user + assistant

        # 第二轮
        _run(_collect(session.send_stream("第二轮")))
        assert len(session.messages) == 5  # + user + assistant

    def test_vision_model_chain(self):
        session = make_session()
        chain = session._vision_model_chain()
        assert len(chain) >= 1
        assert chain[0] == session.vision_model
