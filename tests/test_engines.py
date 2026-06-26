"""Unit tests for generation engines with mocked client."""

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.client import CruxClient
from engines.image_to_image import ImageToImageEngine
from engines.text_to_image import TextToImageEngine
from engines.video import VideoEngine, VideoFuture


class TestTextToImageEngine:
    @pytest.fixture(autouse=True)
    def _isolate_output(self, tmp_path, monkeypatch):
        # 引擎直接把生成的图写到 OUTPUT_DIR/images，必须重定向到临时目录，
        # 否则每次跑测试都会往真实 output/ 写一个 13 字节的垃圾 PNG。
        (tmp_path / "images").mkdir()
        monkeypatch.setattr("engines.text_to_image.OUTPUT_DIR", tmp_path)

    @pytest.fixture
    def mock_client(self):
        c = MagicMock(spec=CruxClient)
        return c

    @pytest.fixture
    def engine(self, mock_client):
        return TextToImageEngine(mock_client)

    def test_generate_returns_dict(self, engine, mock_client):
        fake_b64 = base64.b64encode(b"fake_png_data").decode()
        mock_client.create_image.return_value = {"data": [{"b64_json": fake_b64}]}
        result = engine.generate(prompt="a cat", size="1024x1024")
        assert isinstance(result, dict)
        assert "local_path" in result
        assert result["model"] == "agnes-image-2.1-flash"
        assert result["prompt"] == "a cat"


class TestImageToImageEngine:
    @pytest.fixture
    def mock_client(self):
        c = MagicMock(spec=CruxClient)
        return c

    @pytest.fixture
    def engine(self, mock_client):
        return ImageToImageEngine(mock_client)

    def test_edit_returns_dict(self, engine, mock_client):
        mock_client.create_image.return_value = {"data": [{"url": "https://test.com/img.png"}]}
        mock_client.download_image.return_value = "/tmp/out.png"
        result = engine.edit(prompt="transform", image_urls="https://test.com/src.png", size="1024x1024")
        assert isinstance(result, dict)
        assert "local_path" in result
        assert result["source_images"] == ["https://test.com/src.png"]

    def test_style_transfer_delegates_to_edit(self, engine, mock_client):
        mock_client.create_image.return_value = {"data": [{"url": "https://test.com/out.png"}]}
        mock_client.download_image.return_value = "/tmp/out.png"
        result = engine.style_transfer(prompt="ink wash", image_url="https://test.com/src.png")
        assert isinstance(result, dict)


class TestVideoEngine:
    @pytest.fixture
    def mock_client(self):
        c = MagicMock(spec=CruxClient)
        return c

    @pytest.fixture
    def engine(self, mock_client):
        return VideoEngine(mock_client)

    def test_submit_only_returns_basic_info(self, engine, mock_client):
        mock_client.create_video.return_value = {
            "task_id": "task-123",
            "video_id": "video_abc",
        }
        result = engine.submit_only(prompt="sunset beach", num_frames=81)
        assert result["status"] == "submitted"
        assert result["task_id"] == "task-123"
        assert "video_id" in result

    def test_submit_and_wait_blocks_until_done(self, engine, mock_client):
        mock_client.create_video.return_value = {"task_id": "t1", "video_id": "v1"}
        mock_client.poll_video.return_value = {
            "video_url": "https://test.com/vid.mp4",
            "progress": 100,
            "_timed_out": False,
        }
        mock_client.download_video.return_value = "/tmp/vid.mp4"
        result = engine.submit_and_wait(prompt="waves", num_frames=81)
        assert "local_path" in result

    def test_submit_async_returns_future(self, engine, mock_client):
        mock_client.create_video.return_value = {"task_id": "t2", "video_id": "v2"}
        mock_client.poll_video.return_value = {
            "video_url": "https://test.com/vid2.mp4",
            "progress": 100,
            "_timed_out": False,
        }
        mock_client.download_video.return_value = "/tmp/vid2.mp4"
        future = engine.submit_async(prompt="test", num_frames=81)
        assert isinstance(future, VideoFuture)
        future.wait(timeout=10)
        assert future.is_done()
        result = future.get_result()
        assert "video_id" in result


class TestVideoFuture:
    def test_initial_state(self):
        f = VideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        assert not f.is_done()
        assert f.progress == 0.0
        assert f.status == "submitted"
        assert f.error is None

    def test_cancel_sets_done(self):
        f = VideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        f.cancel()
        assert f.is_done()

    def test_get_result_without_result_raises(self):
        f = VideoFuture(video_id="v1", task_id="t1", prompt="test", num_frames=81)
        f._done.set()
        with pytest.raises(RuntimeError):
            f.get_result()
