"""Unit tests for core/agent.py — ContextManager, parse_plan, PlanStep, PlanExecutor.

agent.py 是 /plan 命令和 agent_mode 的核心模块，但之前零测试覆盖。
覆盖：token 估算、消息截断、依赖检查、plan 解析、状态机。
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import (
    ContextManager, ModelRouter, PlanExecutor, PlanStep,
    StepStatus, compress_messages, parse_plan,
)


# ── ContextManager.estimate_tokens ────────────────────────────────────


class TestEstimateTokens:
    """Token 估算不依赖外部 tokenizer，用启发式。"""

    def test_empty_string(self):
        assert ContextManager.estimate_tokens("") == 0

    def test_pure_ascii(self):
        # narrow: len//4 + 1
        text = "hello"  # 5 chars
        assert ContextManager.estimate_tokens(text) == 5 // 4 + 1  # = 2

    def test_pure_cjk(self):
        # wide: len//2 + 1
        text = "你好世界"  # 4 chars, all wide
        assert ContextManager.estimate_tokens(text) == 4 // 2 + 1  # = 3

    def test_mixed_ascii_cjk(self):
        # 3 narrow + 2 wide → narrow//4 + wide//2 + 1
        text = "abc你好"
        assert ContextManager.estimate_tokens(text) == 3 // 4 + 2 // 2 + 1  # = 3

    def test_longer_text_gives_larger_estimate(self):
        short = "hello world"
        long = "hello world " * 100
        assert ContextManager.estimate_tokens(long) > ContextManager.estimate_tokens(short)


# ── ContextManager.estimate_message_tokens ──────────────────────────


class TestEstimateMessageTokens:
    """消息级别的 token 估算。"""

    def test_simple_text_message(self):
        msg = {"role": "user", "content": "hello"}
        tokens = ContextManager.estimate_message_tokens(msg)
        assert tokens > 0  # content tokens + overhead(4)

    def test_empty_content(self):
        msg = {"role": "user", "content": ""}
        tokens = ContextManager.estimate_message_tokens(msg)
        assert tokens == 4  # overhead only

    def test_multimodal_content_extracts_text(self):
        msg = {"role": "user", "content": [
            {"type": "text", "text": "hello world"},
            {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
        ]}
        tokens = ContextManager.estimate_message_tokens(msg)
        assert tokens > 4  # text content + overhead

    def test_tool_calls_add_tokens(self):
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "/test.py"}'},
            }],
        }
        tokens = ContextManager.estimate_message_tokens(msg)
        assert tokens > 4  # argument tokens + overhead


# ── ContextManager.total_tokens / needs_compression ────────────────────


class TestTotalTokensAndCompression:
    """总量统计和压缩触发判断。"""

    def test_empty_messages_zero_tokens(self):
        cm = ContextManager(max_tokens=100)
        assert cm.total_tokens([]) == 0
        assert cm.needs_compression([]) is False

    def test_total_tokens_includes_all_messages(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        cm = ContextManager(max_tokens=100000)
        total = cm.total_tokens(msgs)
        assert total > 0

    def test_needs_compression_true_when_over_threshold(self):
        long_msg = {"role": "user", "content": "x" * 1000}
        cm = ContextManager(max_tokens=10)  # very low threshold
        assert cm.needs_compression([long_msg]) is True

    def test_needs_compression_false_when_under(self):
        short_msg = {"role": "user", "content": "hi"}
        cm = ContextManager(max_tokens=100000)
        assert cm.needs_compression([short_msg]) is False


# ── ContextManager._truncate_messages ────────────────────────────────


class TestTruncateMessages:
    """单条消息截断——防大文件撑爆上下文。"""

    def test_short_message_unchanged(self):
        cm = ContextManager()
        msgs = [{"role": "user", "content": "hello"}]
        result = cm._truncate_messages(msgs)
        assert result[0]["content"] == "hello"

    def test_oversized_message_truncated(self):
        cm = ContextManager()
        # 超过 8000 字符的消息
        long_content = "A" * 20000
        msgs = [{"role": "tool", "content": long_content}]
        result = cm._truncate_messages(msgs)
        assert len(result[0]["content"]) < 20000
        assert "truncated" in result[0]["content"]
        # 验证保留了头部和尾部
        assert result[0]["content"].startswith("A")
        assert result[0]["content"].endswith("A")

    def test_non_string_content_passed_through(self):
        cm = ContextManager()
        msgs = [{"role": "user", "content": 42}]
        result = cm._truncate_messages(msgs)
        assert result[0]["content"] == 42

    def test_multiline_content_preserves_structure(self):
        cm = ContextManager()
        content = "line\n" * 20000
        msgs = [{"role": "tool", "content": content}]
        result = cm._truncate_messages(msgs)
        assert "truncated" in result[0]["content"]


# ── parse_plan ─────────────────────────────────────────────────────────


class TestParsePlan:
    """从 LLM 输出文本解析执行计划。"""

    def test_parse_fenced_code_block(self):
        text = """分析完成，计划如下：

```plan
1. [setup] Purpose: 创建项目结构 - Tool: run_bash
2. [implement] Purpose: 编写核心逻辑 - Tool: write_file - depends: 1
3. [test] Purpose: 运行测试验证 - Tool: run_test - depends: 1,2
```

开始执行。"""
        steps = parse_plan(text)
        assert len(steps) == 3
        assert steps[0].name == "setup"
        assert steps[0].purpose == "创建项目结构"
        assert steps[0].tool == "run_bash"
        assert steps[0].depends_on == []

    def test_parse_numbered_list_fallback(self):
        text = "1. 创建文件\n2. 编写测试\ndone"
        steps = parse_plan(text)
        assert len(steps) == 2

    def test_parse_empty_text(self):
        assert parse_plan("") == []

    def test_parse_no_plan_block(self):
        assert parse_plan("这里没有计划") == []

    def test_parse_dependencies(self):
        text = """```plan
1. [setup] Tool: bash
2. [code] depends: 1
3. [test] depends: 1,2
```"""
        steps = parse_plan(text)
        assert steps[1].depends_on == [1]
        assert steps[2].depends_on == [1, 2]

    def test_parse_chinese_tool_label(self):
        text = """```plan
1. [setup] 工具: run_bash
```"""
        steps = parse_plan(text)
        assert steps[0].tool == "run_bash"


# ── PlanStep ───────────────────────────────────────────────────────────


class TestPlanStep:
    """PlanStep 数据对象和状态机。"""

    def test_default_status_is_pending(self):
        step = PlanStep(name="test")
        assert step.status == StepStatus.PENDING

    def test_to_dict_roundtrip_keys(self):
        step = PlanStep(name="deploy", purpose="部署", tool="bash", depends_on=[1, 2])
        d = step.to_dict()
        assert d["name"] == "deploy"
        assert d["purpose"] == "部署"
        assert d["tool"] == "bash"
        assert d["depends_on"] == [1, 2]
        assert d["status"] == "pending"

    def test_to_dict_truncates_long_result(self):
        step = PlanStep(name="test")
        step.result = "x" * 1000
        d = step.to_dict()
        assert len(d["result"]) <= 500

    def test_empty_dependencies_defaults_to_empty_list(self):
        step = PlanStep(name="test")
        assert step.depends_on == []


# ── PlanExecutor ──────────────────────────────────────────────────────


class TestPlanExecutor:
    """PlanExecutor 执行流程——依赖、重试、状态转换。"""

    def test_execute_single_step(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "done: created file"}}]
        }
        executor = PlanExecutor(client=mock_client)
        step = PlanStep(name="create-file", tool="write_file")
        results = executor.execute([step])
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETED
        assert "created file" in results[0].result

    def test_execute_respects_dependencies(self):
        mock_client = MagicMock()
        executor = PlanExecutor(client=mock_client)
        # step 2 depends on step 1 — if step 1 fails, step 2 should skip
        step1 = PlanStep(name="setup", tool="bash")
        step2 = PlanStep(name="implement", depends_on=[1])
        # Mock _execute_step to fail on step 1
        with patch.object(executor, '_execute_step', side_effect=RuntimeError("fail")):
            results = executor.execute([step1, step2])
        assert results[0].status == StepStatus.FAILED
        assert results[1].status == StepStatus.SKIPPED
        assert "Dependency" in results[1].error

    def test_execute_retry_on_failure(self):
        call_count = 0

        def flaky_execute(step, ctx):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return "success on retry"

        mock_client = MagicMock()
        executor = PlanExecutor(client=mock_client)
        step = PlanStep(name="test", tool="run_test")
        with patch.object(executor, '_execute_step', side_effect=flaky_execute):
            results = executor.execute([step])
        assert results[0].status == StepStatus.COMPLETED
        assert call_count == 2  # first failed, second succeeded

    def test_execute_skips_beyond_max_steps(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        executor = PlanExecutor(client=mock_client, model="test-model")
        executor.max_steps = 2
        steps = [PlanStep(name=f"step-{i}") for i in range(5)]
        results = executor.execute(steps)
        assert len(results) == 2  # capped at max_steps
