"""Tests for core.providers.agnes — AgnesProvider 核心方法（离线部分）"""
from core.providers.agnes import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_VIDEO_MODEL,
    VALID_IMAGE_SIZES,
    VALID_VIDEO_FRAMES,
    AgnesProvider,
    _clean_video_id,
)


class TestCleanVideoId:
    def test_plain_id_passthrough(self):
        assert _clean_video_id("video_abc123") == "video_abc123"

    def test_empty(self):
        assert _clean_video_id("") == ""

    def test_none(self):
        assert _clean_video_id("") == ""  # None would fail at isinstance check

    def test_litellm_wrapped(self):
        import base64
        inner = "litellm:custom_llm_provider:openai;model_id:agnes-video-v2.0;video_id:video_real123"
        wrapped = "video_" + base64.b64encode(inner.encode()).decode()
        assert _clean_video_id(wrapped) == "video_real123"

    def test_plaintext_wrapped(self):
        # litellm wrapped plaintext with ;video_id: separator
        raw = "video_litellm:custom_llm_provider:openai;video_id:video_plain456"
        assert _clean_video_id(raw) == "video_plain456"


class TestAgnesProviderInit:
    def test_init_defaults(self):
        p = AgnesProvider()
        assert p.api_key != ""
        assert "apihub.agnes-ai.com" in p.base_url
        p.close()

    def test_custom_params(self):
        p = AgnesProvider(api_key="test-key", base_url="https://test.example.com/v1")
        assert p.api_key == "test-key"
        assert p.base_url == "https://test.example.com/v1"
        p.close()


class TestImageValidation:
    def test_valid_sizes(self):
        p = AgnesProvider()
        for s in ["1024x768", "768x1024", "1024x1024", "576x1024", "1024x576"]:
            assert p._validate_image_size(s) == s
        p.close()

    def test_invalid_defaults(self):
        p = AgnesProvider()
        assert p._validate_image_size("999x999") == "1024x768"
        p.close()


class TestVideoValidation:
    def test_valid_frames(self):
        p = AgnesProvider()
        for nf in [81, 121, 161, 201, 241, 281, 321, 361, 401, 441]:
            assert p._validate_num_frames(nf) == nf
        p.close()

    def test_invalid_frames_map(self):
        p = AgnesProvider()
        assert p._validate_num_frames(100) == 121  # maps up
        assert p._validate_num_frames(500) == 441  # capped
        p.close()

    def test_size_align(self):
        p = AgnesProvider()
        # 64-aligned
        s = p._validate_video_size("1024x768")
        w, h = map(int, s.split("x"))
        assert w % 64 == 0
        assert h % 64 == 0
        p.close()

    def test_frame_rate(self):
        p = AgnesProvider()
        assert p._validate_frame_rate(24) == 24
        assert p._validate_frame_rate(0) == 1
        assert p._validate_frame_rate(999) == 60
        p.close()


class TestInferSizeFromText:
    def test_portrait_chinese(self):
        assert AgnesProvider.infer_size_from_text("竖屏视频") == "768x1024"

    def test_landscape(self):
        assert AgnesProvider.infer_size_from_text("横屏 16:9") == "1024x768"

    def test_square(self):
        assert AgnesProvider.infer_size_from_text("方图 1:1") == "1024x1024"

    def test_reels(self):
        assert AgnesProvider.infer_size_from_text("make a reels") == "768x1024"

    def test_youtube(self):
        assert AgnesProvider.infer_size_from_text("youtube video") == "1024x768"

    def test_default(self):
        assert AgnesProvider.infer_size_from_text("普通视频") == "1024x768"


class TestDefaults:
    def test_image_model(self):
        assert "agnes-image-2.1" in DEFAULT_IMAGE_MODEL

    def test_video_model(self):
        assert "agnes-video" in DEFAULT_VIDEO_MODEL

    def test_valid_sizes_whitelist(self):
        assert "1024x768" in VALID_IMAGE_SIZES
        assert "768x1024" in VALID_IMAGE_SIZES
        assert "1024x1024" in VALID_IMAGE_SIZES
        assert "576x1024" in VALID_IMAGE_SIZES

    def test_valid_video_frames_whitelist(self):
        assert 81 in VALID_VIDEO_FRAMES
        assert 121 in VALID_VIDEO_FRAMES
        assert 441 in VALID_VIDEO_FRAMES
        assert 50 not in VALID_VIDEO_FRAMES
