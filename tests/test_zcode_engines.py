"""Smoke tests for engines/ layer — instantiation, key methods, parameter validation.

RED-GREEN: Run with `pytest tests/test_zcode_engines.py -v`
"""

from unittest.mock import Mock, patch

import pytest

from core.async_client import AsyncCruxClient
from core.client import CruxClient
from core.validator import validate_image_size, validate_num_frames, validate_seed, validate_video_resolution

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_sync_client():
    """A CruxClient with mocked HTTP transport — no real API calls."""
    client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")
    client._http = Mock()
    client._http.post = Mock()
    return client


@pytest.fixture
def mock_async_client():
    """An AsyncCruxClient with mocked HTTP transport."""
    client = AsyncCruxClient(api_key="fake-key", base_url="http://localhost:9999")
    client._http = Mock()
    return client


# ═══════════════════════════════════════════════════════════════════════
# TextToImageEngine
# ═══════════════════════════════════════════════════════════════════════


class TestTextToImageEngine:
    """Smoke: instantiation, key method existence, parameter validation."""

    def test_instantiate_with_mock_client(self, mock_sync_client):
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(mock_sync_client)
        assert engine.client is mock_sync_client

    def test_has_key_methods(self, mock_sync_client):
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(mock_sync_client)
        assert callable(engine.generate)
        assert callable(engine.generate_batch)

    def test_get_model_returns_default(self, mock_sync_client):
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(mock_sync_client)
        model = engine._get_model()
        assert isinstance(model, str)
        assert len(model) > 0

    def test_get_model_returns_explicit(self, mock_sync_client):
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(mock_sync_client)
        assert engine._get_model("my-custom-model") == "my-custom-model"

    def test_size_validation(self):
        assert validate_image_size("1024x768") == "1024x768"
        assert validate_image_size("1024x1024") == "1024x1024"

    def test_seed_validation(self):
        assert validate_seed(None) is None
        assert validate_seed(42) == 42
        assert validate_seed(-10) == 0
        assert validate_seed(2**32) == 2**31 - 1

    def test_generate_rejects_bad_api_response(self, mock_sync_client):
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(mock_sync_client)
        mock_sync_client.create_image = Mock(return_value={"bad": "no data key"})
        with (
            patch("engines.text_to_image.validate_model", return_value="fake-model"),
            pytest.raises(RuntimeError),
        ):
            engine.generate("a cat")


class TestAsyncTextToImageEngine:
    """Smoke: async counterpart instantiation and key methods."""

    def test_instantiate_with_mock_client(self, mock_async_client):
        from engines.text_to_image import AsyncTextToImageEngine

        engine = AsyncTextToImageEngine(mock_async_client)
        assert engine.client is mock_async_client

    def test_has_key_methods(self, mock_async_client):
        from engines.text_to_image import AsyncTextToImageEngine

        engine = AsyncTextToImageEngine(mock_async_client)
        assert callable(engine.generate)
        assert callable(engine.generate_batch)


# ═══════════════════════════════════════════════════════════════════════
# ImageToImageEngine
# ═══════════════════════════════════════════════════════════════════════


class TestImageToImageEngine:
    """Smoke: instantiation, key method existence, url validation."""

    def test_instantiate_with_mock_client(self, mock_sync_client):
        from engines.image_to_image import ImageToImageEngine

        engine = ImageToImageEngine(mock_sync_client)
        assert engine.client is mock_sync_client

    def test_has_key_methods(self, mock_sync_client):
        from engines.image_to_image import ImageToImageEngine

        engine = ImageToImageEngine(mock_sync_client)
        assert callable(engine.edit)
        assert callable(engine.compose)
        assert callable(engine.style_transfer)
        assert callable(engine.edit_with_21)

    def test_get_model_returns_default(self, mock_sync_client):
        from engines.image_to_image import ImageToImageEngine

        engine = ImageToImageEngine(mock_sync_client)
        model = engine._get_model()
        assert isinstance(model, str)
        assert len(model) > 0


class TestAsyncImageToImageEngine:
    """Smoke: async counterpart instantiation and key methods."""

    def test_instantiate_with_mock_client(self, mock_async_client):
        from engines.image_to_image import AsyncImageToImageEngine

        engine = AsyncImageToImageEngine(mock_async_client)
        assert engine.client is mock_async_client

    def test_has_key_methods(self, mock_async_client):
        from engines.image_to_image import AsyncImageToImageEngine

        engine = AsyncImageToImageEngine(mock_async_client)
        assert callable(engine.edit)
        assert callable(engine.compose)
        assert callable(engine.style_transfer)
        assert callable(engine.edit_with_21)


# ═══════════════════════════════════════════════════════════════════════
# VideoEngine + VideoFuture
# ═══════════════════════════════════════════════════════════════════════


class TestVideoFuture:
    """Smoke: VideoFuture lifecycle — creation, progress, wait, result."""

    def test_initial_state(self):
        from engines.video import VideoFuture

        f = VideoFuture("vid_1", "task_1", "a cat", 121)
        assert f.video_id == "vid_1"
        assert f.task_id == "task_1"
        assert f.progress == 0.0
        assert f.status == "submitted"
        assert f.is_done() is False
        assert f.error is None

    def test_wait_timeout(self):
        from engines.video import VideoFuture

        f = VideoFuture("vid_2", "task_2", "a dog", 81)
        # Not done, should timeout
        assert f.wait(timeout=0.01) is False

    def test_get_result_raises_when_no_result(self):
        from engines.video import VideoFuture

        f = VideoFuture("vid_3", "task_3", "a bird", 161)
        # Mark done but no result set
        f._done.set()
        with pytest.raises(RuntimeError, match="no result"):
            f.get_result()

    def test_get_result_raises_when_error(self):
        from engines.video import VideoFuture

        f = VideoFuture("vid_4", "task_4", "a fish", 201)
        f._error = RuntimeError("poll failed")
        f._done.set()
        with pytest.raises(RuntimeError, match="poll failed"):
            f.get_result()

    def test_cancel(self):
        from engines.video import VideoFuture

        f = VideoFuture("vid_5", "task_5", "cancel me", 121)
        f.cancel()
        assert f.is_done() is True


class TestVideoEngine:
    """Smoke: instantiation and key method existence."""

    def test_instantiate_with_mock_client(self, mock_sync_client):
        from engines.video import VideoEngine

        engine = VideoEngine(mock_sync_client)
        assert engine.client is mock_sync_client

    def test_has_submit_methods(self, mock_sync_client):
        from engines.video import VideoEngine

        engine = VideoEngine(mock_sync_client)
        assert callable(engine.submit_only)
        assert callable(engine.submit_async)
        assert callable(engine.submit_and_wait)

    def test_has_convenience_methods(self, mock_sync_client):
        from engines.video import VideoEngine

        engine = VideoEngine(mock_sync_client)
        assert callable(engine.text_to_video)
        assert callable(engine.image_to_video)
        assert callable(engine.multi_image_video)
        assert callable(engine.keyframe_animation)

    def test_submit_only_returns_expected_keys(self, mock_sync_client):
        from engines.video import VideoEngine

        engine = VideoEngine(mock_sync_client)
        mock_sync_client.create_video = Mock(return_value={"task_id": "t123", "video_id": "video_abc"})
        result = engine.submit_only("a cat")
        assert "task_id" in result
        assert "video_id" in result
        assert result["status"] == "submitted"

    def test_get_model_returns_string(self, mock_sync_client):
        from engines.video import VideoEngine

        engine = VideoEngine(mock_sync_client)
        model = engine._get_model()
        assert isinstance(model, str)
        assert len(model) > 0


class TestAsyncVideoFuture:
    """Smoke: AsyncVideoFuture lifecycle."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        from engines.video import AsyncVideoFuture

        f = AsyncVideoFuture("vid_a1", "task_a1", "async cat", 121)
        assert f.video_id == "vid_a1"
        assert f.progress == 0.0
        assert f.status == "submitted"
        assert f.is_done() is False

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        from engines.video import AsyncVideoFuture

        f = AsyncVideoFuture("vid_a2", "task_a2", "async dog", 81)
        assert await f.wait(timeout=0.01) is False

    @pytest.mark.asyncio
    async def test_cancel(self):
        from engines.video import AsyncVideoFuture

        f = AsyncVideoFuture("vid_a3", "task_a3", "cancel async", 121)
        f.cancel()
        assert f.is_done() is True


class TestAsyncVideoEngine:
    """Smoke: async video engine instantiation and key methods."""

    def test_instantiate_with_mock_client(self, mock_async_client):
        from engines.video import AsyncVideoEngine

        engine = AsyncVideoEngine(mock_async_client)
        assert engine.client is mock_async_client

    def test_has_key_methods(self, mock_async_client):
        from engines.video import AsyncVideoEngine

        engine = AsyncVideoEngine(mock_async_client)
        assert callable(engine.submit_only)
        assert callable(engine.submit_async)
        assert callable(engine.submit_and_wait)
        assert callable(engine.text_to_video)
        assert callable(engine.image_to_video)

    @pytest.mark.asyncio
    async def test_submit_only_async(self, mock_async_client):
        from engines.video import AsyncVideoEngine

        engine = AsyncVideoEngine(mock_async_client)
        mock_async_client.create_video = Mock(return_value={"task_id": "t456", "video_id": "video_xyz"})

        # Wrap sync mock result so await works
        async def _mock_create_video(**kw):
            return {"task_id": "t456", "video_id": "video_xyz"}

        mock_async_client.create_video = _mock_create_video
        result = await engine.submit_only("async cat")
        assert result["task_id"] == "t456"
        assert result["status"] == "submitted"


# ═══════════════════════════════════════════════════════════════════════
# Video params validation
# ═══════════════════════════════════════════════════════════════════════


class TestVideoParamsValidation:
    """Parameter validation for video engine inputs."""

    def test_num_frames_valid(self):
        assert validate_num_frames(121) == 121
        assert validate_num_frames(81) == 81
        assert validate_num_frames(441) == 441

    def test_num_frames_clamped(self):
        # Below minimum
        assert validate_num_frames(1) == 81
        # Above maximum
        assert validate_num_frames(999) == 441
        # Non-standard → nearest valid
        result = validate_num_frames(100)
        assert result in [81, 121, 161, 201, 241, 281, 321, 361, 401, 441]

    def test_video_resolution_exact_match(self):
        w, h = validate_video_resolution(1024, 768)
        assert (w, h) == (1024, 768)
        w2, h2 = validate_video_resolution(1280, 720)
        assert (w2, h2) == (1280, 720)

    def test_video_resolution_fallback(self):
        # Non-preset resolution → matches closest
        w, h = validate_video_resolution(1920, 1080)
        assert w > 0
        assert h > 0


# ═══════════════════════════════════════════════════════════════════════
# BatchVariantEngine
# ═══════════════════════════════════════════════════════════════════════


class TestBatchVariantEngine:
    """Smoke: batch variant engine instantiation and count clamping."""

    def test_instantiate_with_mock_client(self, mock_sync_client):
        from engines.batch_grid import BatchVariantEngine

        engine = BatchVariantEngine(mock_sync_client)
        assert engine.client is mock_sync_client
        assert engine.t2i is not None

    def test_has_generate_variants(self, mock_sync_client):
        from engines.batch_grid import BatchVariantEngine

        engine = BatchVariantEngine(mock_sync_client)
        assert callable(engine.generate_variants)

    def test_grid_cols_rules(self):
        from engines.batch_grid import _grid_cols

        assert _grid_cols(1) == 1
        assert _grid_cols(3) == 2
        assert _grid_cols(4) == 2
        assert _grid_cols(6) == 3
        assert _grid_cols(9) == 3


# ═══════════════════════════════════════════════════════════════════════
# Validator edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestValidatorEdgeCases:
    """Edge case tests for shared validators."""

    def test_image_size_invalid_format(self):
        from core.validator import ValidationError

        with pytest.raises(ValidationError):
            validate_image_size("not-a-size")

    def test_image_urls_empty(self):
        from core.validator import ValidationError, validate_image_urls

        with pytest.raises(ValidationError):
            validate_image_urls([])

    def test_image_urls_bad_protocol(self):
        from core.validator import ValidationError, validate_image_urls

        with pytest.raises(ValidationError):
            validate_image_urls("ftp://bad-protocol/image.png")

    def test_image_urls_single_string(self):
        from core.validator import validate_image_urls

        result = validate_image_urls("https://example.com/img.png")
        assert result == ["https://example.com/img.png"]

    def test_image_urls_valid_list(self):
        from core.validator import validate_image_urls

        urls = ["https://a.com/1.png", "https://b.com/2.jpg"]
        result = validate_image_urls(urls)
        assert result == urls

    def test_image_urls_data_uri(self):
        from core.validator import validate_image_urls

        result = validate_image_urls("data:image/png;base64,abc123")
        assert len(result) == 1
