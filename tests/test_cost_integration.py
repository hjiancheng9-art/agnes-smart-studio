"""Tests for #6 cost_tracker runtime integration.

验证 cost_tracker 真正被 ChatSession 调用（此前是零调用方孤岛）。
覆盖三个埋点：
1. _dispatch_tool 的 generate_image 分支 → record_usage(kind=image)
2. _dispatch_tool 的 generate_video 分支 → record_usage(kind=video)
3. send_stream 开头 → check_budget 超限时 yield info 警告

不测 _vision_fallback 的视觉埋点（需 mock vision_client 返回带 usage 的响应，
且该路径在多模态分支内、逻辑复杂，留给手动验证；此处聚焦可稳定测试的路径）。
"""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolate_cost_files(tmp_path, monkeypatch):
    """把 COST_LOG/COST_STATE 重定向到 tmp_path，避免污染真实文件。"""
    import core.cost_tracker as ct
    monkeypatch.setattr(ct, "COST_LOG", tmp_path / "cost_log.jsonl")
    monkeypatch.setattr(ct, "COST_STATE", tmp_path / "cost_state.json")
    ct._save_state({"total_cost": 0.0, "total_calls": 0, "budget": None,
                    "by_model": {}, "by_day": {}, "by_kind": {}})
    yield tmp_path


def _mocked_session():
    """构造一个 mock client 的 ChatSession（不打真实 API）。"""
    from core.chat import ChatSession
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter([])
    return ChatSession(mock_client)


class TestGenerateImageRecordsCost:
    """generate_image 工具成功后应写 cost_log。"""

    def test_image_generation_logs_cost(self, isolate_cost_files):
        from core.chat import ChatSession
        session = _mocked_session()
        # mock brain + t2i，让 generate 成功
        session.brain = MagicMock()
        session.brain.enhance_image_prompt.return_value = {"optimized_prompt": "x", "negative_prompt": ""}
        session.t2i = MagicMock()
        session.t2i.generate.return_value = {"local_path": "/tmp/a.png"}

        text, side = ChatSession._dispatch_tool(session, "generate_image",
                                                 '{"prompt": "a cat"}')
        assert "已生成" in text

        # cost_log 应有一条 image 记录
        import core.cost_tracker as ct
        log_lines = ct.COST_LOG.read_text(encoding="utf-8").strip().split("\n")
        assert len(log_lines) == 1
        entry = json.loads(log_lines[0])
        assert entry["kind"] == "image"
        assert entry["label"] == "generate_image"
        assert entry["cost"] > 0
        # state 累加也应更新
        state = ct.get_summary()
        assert state["total_calls"] == 1
        assert state["by_kind"]["image"]["calls"] == 1


class TestGenerateVideoRecordsCost:
    """generate_video 工具成功后应写 cost_log。"""

    def test_video_generation_logs_cost(self, isolate_cost_files):
        from core.chat import ChatSession
        session = _mocked_session()
        session.brain = MagicMock()
        session.brain.enhance_video_prompt.return_value = {"optimized_prompt": "x", "negative_prompt": ""}
        session.vid = MagicMock()
        session.vid.text_to_video.return_value = {"local_path": "/tmp/a.mp4", "status": "completed"}

        text, side = ChatSession._dispatch_tool(session, "generate_video",
                                                 '{"prompt": "a running cat"}')
        assert "已生成" in text

        import core.cost_tracker as ct
        log_lines = ct.COST_LOG.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(log_lines[0])
        assert entry["kind"] == "video"
        assert entry["label"] == "generate_video"
        # 视频按次计费 0.35
        assert abs(entry["cost"] - 0.35) < 1e-6


class TestBudgetWarningInSendStream:
    """超预算时 send_stream 开头应 yield info 警告（不阻断）。"""

    def test_budget_warning_yielded_when_exceeded(self, isolate_cost_files):
        import core.cost_tracker as ct
        # 设一个极低预算，然后记一笔花费使其超限
        ct.set_budget(0.01)
        ct.record_usage(model="agnes-video-v2.0", kind="video", label="test")

        session = _mocked_session()
        # 让 chat_stream 立即结束（无 tool_calls，无内容）
        session.client.chat_stream.return_value = iter([
            {"content": "ok", "_finish": "stop"}
        ])
        outputs = list(session.send_stream("hello"))
        # 应至少有一个 info 类型的预算警告
        warnings = [p for k, p in outputs if k == "info" and "预算" in str(p)]
        assert len(warnings) >= 1, f"应有预算警告，实际 outputs: {outputs}"

    def test_no_warning_when_under_budget(self, isolate_cost_files):
        """未超预算时不 yield 警告。"""
        import core.cost_tracker as ct
        ct.set_budget(100.0)  # 很高，不会超

        session = _mocked_session()
        session.client.chat_stream.return_value = iter([
            {"content": "hi", "_finish": "stop"}
        ])
        outputs = list(session.send_stream("hello"))
        warnings = [p for k, p in outputs if k == "info" and "预算" in str(p)]
        assert len(warnings) == 0

    def test_no_budget_set_no_warning(self, isolate_cost_files):
        """未设预算（budget=None）时 check_budget 返回 None，不 yield。"""
        session = _mocked_session()
        session.client.chat_stream.return_value = iter([
            {"content": "hi", "_finish": "stop"}
        ])
        outputs = list(session.send_stream("hello"))
        warnings = [p for k, p in outputs if k == "info" and "预算" in str(p)]
        assert len(warnings) == 0


class TestCostTrackerImportSafety:
    """cost_tracker 不可用时应静默降级，不阻断生成。"""

    def test_generate_image_survives_cost_import_failure(self, isolate_cost_files, monkeypatch):
        """模拟 cost_tracker 导入失败（ImportError），generate_image 仍应正常返回。"""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "core.cost_tracker" or name.endswith(".cost_tracker"):
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from core.chat import ChatSession
        session = _mocked_session()
        session.brain = MagicMock()
        session.brain.enhance_image_prompt.return_value = {"optimized_prompt": "x", "negative_prompt": ""}
        session.t2i = MagicMock()
        session.t2i.generate.return_value = {"local_path": "/tmp/a.png"}

        text, side = ChatSession._dispatch_tool(session, "generate_image",
                                                 '{"prompt": "a cat"}')
        # 即使 cost_tracker 不可用，生成仍成功
        assert "已生成" in text
