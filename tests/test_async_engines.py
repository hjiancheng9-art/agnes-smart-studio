"""Unit tests for async generation engines with mocked AsyncCruxClient.

Covers AsyncTextToImageEngine / AsyncImageToImageEngine / AsyncVideoEngine /
AsyncVideoFuture / AsyncSmartBrain — the asyncio-native mirrors of the sync
engines. These tests run without real network I/O: every await on the client
returns a MagicMock-wrapped coroutine.
"""
import sys
import asyncio
import base64
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.async_client import AsyncCruxClient
from engines.text_to_image import AsyncTextToImageEngine
from engines.image_to_image import AsyncImageToImageEngine
from engines.video import AsyncVideoEngine, AsyncVideoFuture


def _async_value(value):
    """Build an AsyncMock that resolves to `value` (or raises if it's an Exception)."""
    m = AsyncMock()
    if isinstance(value, Exception):
        m.side_effect = value
    else:
        m.return_value = value
    return m


def _make_async_mock_client():
    """A MagicMock with spec=AsyncCruxClient.

    spec keeps the attribute set constrained to the real class so typo'd
    method names still raise AttributeError. Individual tests then assign
    AsyncMock return values to the specific methods they exercise.
    """
    return MagicMock(spec=AsyncCruxClient)


# ═══════════════════════════════════════════════════════════════
# AsyncTextToImageEngine
# ═══════════════════════════════════════════════════════════════

class TestAsyncTextToImageEngine:
    @pytest.fixture(autouse=True)
    def _isolate_output(self, tmp_path, monkeypatch):
        # 引擎直接把生成的图写到 OUTPUT_DIR/images，必须重定向到临时目录
        (tmp_path / "images").mkdir()
        monkeypatch.setattr("engines.text_to_image.OUTPUT_DIR", tmp_path)

    @pytest.fixture
    def mock_client(self):
        return _make_async_mock_client()

    @pytest.fixture
    def engine(self, mock_client):
        return AsyncTextToImageEngine(mock_client)

    def test_generate_returns_dict_with_b64(self, engine, mock_client):
        fake_b64 = base64.b64encode(b"fake_png_data").decode()
        mock_client.create_image = _async_value({"data": [{"b64_json": fake_b64}]})
        # BYPASS_ENABLED 默认关闭，prompt_bypass 直接走 _gen
        result = asyncio.run(
            engine.generate(prompt="a cat", size="1024x1024")
        )
        assert isinstance(result, dict)
        assert "local_path" in result
        assert result["model"] == "agnes-image-2.1-flash"
        assert result["prompt"] == "a cat"

    def test_generate_with_url_downloads(self, engine, mock_client):
        mock_client.create_image = _async_value(
            {"data": [{"url": "https://cdn.test/img.png"}]}
        )
        mock_client.download_image = _async_value("/tmp/out.png")
        result = asyncio.run(
            engine.generate(prompt="sky", size="1024x768", return_url=True)
        )
        assert result["url"] == "https://cdn.test/img.png"

    def test_generate_batch_runs_in_parallel(self, engine, mock_client):
        # 每次调用返回不同的 b64，验证 gather 并行语义
        def _make_resp(prompt):
            return {"data": [{"b64_json": base64.b64encode(prompt.encode()).decode()}]}

        async def _side_effect(**kw):
            return _make_resp(kw["prompt"])

        mock_client.create_image = AsyncMock(side_effect=_side_effect)
        results = asyncio.run(
            engine.generate_batch(["aa", "bb", "cc"])
        )
        assert len(results) == 3
        # 每个结果携带各自 prompt（说明并行调用各自返回）
        prompts = {r["prompt"] for r in results}
        assert prompts == {"aa", "bb", "cc"}


# ═══════════════════════════════════════════════════════════════
# AsyncImageToImageEngine
# ═══════════════════════════════════════════════════════════════

class TestAsyncImageToImageEngine:
    @pytest.fixture(autouse=True)
    def _isolate_output(self, tmp_path, monkeypatch):
        (tmp_path / "images").mkdir()
        monkeypatch.setattr("engines.image_to_image.OUTPUT_DIR", tmp_path)

    @pytest.fixture
    def mock_client(self):
        return _make_async_mock_client()

    @pytest.fixture
    def engine(self, mock_client):
        return AsyncImageToImageEngine(mock_client)

    def test_edit_returns_dict(self, engine, mock_client):
        mock_client.create_image = _async_value(
            {"data": [{"url": "https://test.com/img.png"}]}
        )
        mock_client.download_image = _async_value("/tmp/out.png")
        result = asyncio.run(
            engine.edit(prompt="transform", image_urls="https://src.png",
                        size="1024x1024")
        )
        assert isinstance(result, dict)
        assert "local_path" in result
        assert result["source_images"] == ["https://src.png"]

    def test_style_transfer_delegates_to_edit(self, engine, mock_client):
        mock_client.create_image = _async_value(
            {"data": [{"url": "https://test.com/out.png"}]}
        )
        mock_client.download_image = _async_value("/tmp/out.png")
        result = asyncio.run(
            engine.style_transfer(prompt="ink wash", image_url="https://src.png")
        )
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# AsyncVideoEngine
# ═══════════════════════════════════════════════════════════════

class TestAsyncVideoEngine:
    @pytest.fixture(autouse=True)
    def _isolate_output(self, tmp_path, monkeypatch):
        (tmp_path / "videos").mkdir()
        monkeypatch.setattr("engines.video.OUTPUT_DIR", tmp_path)

    @pytest.fixture
    def mock_client(self):
        return _make_async_mock_client()

    @pytest.fixture
    def engine(self, mock_client):
        return AsyncVideoEngine(mock_client)

    def test_submit_only_returns_basic_info(self, engine, mock_client):
        mock_client.create_video = _async_value(
            {"task_id": "task-123", "video_id": "video_abc"}
        )
        result = asyncio.run(
            engine.submit_only(prompt="sunset beach", num_frames=81)
        )
        assert result["status"] == "submitted"
        assert result["task_id"] == "task-123"
        assert result["video_id"] == "video_abc"

    def test_submit_and_wait_blocks_until_done(self, engine, mock_client):
        mock_client.create_video = _async_value(
            {"task_id": "t1", "video_id": "v1"}
        )
        mock_client.poll_video = _async_value(
            {"video_url": "https://test.com/vid.mp4", "progress": 100,
             "_timed_out": False}
        )
        mock_client.download_video = _async_value("/tmp/vid.mp4")
        result = asyncio.run(
            engine.submit_and_wait(prompt="waves", num_frames=81)
        )
        assert "local_path" in result

    def test_submit_async_returns_future_and_completes(self, engine, mock_client):
        mock_client.create_video = _async_value(
            {"task_id": "t2", "video_id": "v2"}
        )
        mock_client.poll_video = _async_value(
            {"video_url": "https://test.com/vid2.mp4", "progress": 100,
             "_timed_out": False}
        )
        mock_client.download_video = _async_value("/tmp/vid2.mp4")
        loop = asyncio.new_event_loop()
        try:
            future = loop.run_until_complete(
                engine.submit_async(prompt="test", num_frames=81)
            )
            assert isinstance(future, AsyncVideoFuture)
            done = loop.run_until_complete(future.wait(timeout=10))
            assert done is True
            result = loop.run_until_complete(future.get_result())
            assert "video_id" in result
        finally:
            loop.close()


# ═══════════════════════════════════════════════════════════════
# AsyncVideoFuture — 属性契约
# ═══════════════════════════════════════════════════════════════

class TestAsyncVideoFuture:
    def test_initial_state_properties_are_sync(self):
        """属性 progress/status/error 必须是同步 getter，不可返回协程。
        之前版本误用 @property + async def，访问会返回 coroutine 对象。
        """
        f = AsyncVideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        # 这些必须是即时值，不是 coroutine
        assert f.progress == 0.0
        assert f.status == "submitted"
        assert f.error is None
        assert f.is_done() is False

    def test_cancel_sets_done(self):
        f = AsyncVideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        f.cancel()
        assert f.is_done()

    def test_get_result_without_result_raises(self):
        f = AsyncVideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        f._done.set()
        with pytest.raises(RuntimeError):
            asyncio.run(f.get_result())

    def test_wait_with_timeout_returns_false(self):
        f = AsyncVideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        loop = asyncio.new_event_loop()
        try:
            done = loop.run_until_complete(f.wait(timeout=0.05))
            assert done is False
        finally:
            loop.close()


# ═══════════════════════════════════════════════════════════════
# AsyncSmartBrain — _ask_brain 与 enhance_* 的契约
# ═══════════════════════════════════════════════════════════════

class TestAsyncSmartBrain:
    def test_ask_brain_strips_json_fence(self):
        from core.brain import AsyncSmartBrain

        client = _make_async_mock_client()
        # 模拟模型返回被 ```json 包裹的 JSON
        client.chat = _async_value({
            "choices": [{"message": {"content": "```json\n{\"k\": 1}\n```"}}]
        })
        brain = AsyncSmartBrain(client)
        loop = asyncio.new_event_loop()
        try:
            text = loop.run_until_complete(
                brain._ask_brain("sys", "usr")
            )
            # 去除 fence 后应是纯 JSON
            assert "```" not in text
            assert text.strip().startswith("{")
        finally:
            loop.close()

    def test_enhance_image_prompt_delegates_postprocess(self):
        """enhance_image_prompt 应复用 SmartBrain 后处理逻辑，
        返回带 optimized_prompt / negative_prompt 的 dict。
        """
        from core.brain import AsyncSmartBrain

        client = _make_async_mock_client()
        # 后处理需要一个 JSON 响应作为 brain 文本
        brain_resp = '{"optimized_prompt": "a serene lake"}'
        client.chat = _async_value({
            "choices": [{"message": {"content": brain_resp}}]
        })
        brain = AsyncSmartBrain(client)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                brain.enhance_image_prompt("a lake at sunset")
            )
            assert isinstance(result, dict)
            assert "optimized_prompt" in result
            assert "negative_prompt" in result
        finally:
            loop.close()
