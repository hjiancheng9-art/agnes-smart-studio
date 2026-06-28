"""Tests for core/zhipu_generator.py — Zhipu GLM image/video generator utilities."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.zhipu_generator import (
    get_zhipu_api_key,
    generate_image,
    generate_video,
    poll_video,
    zhipu_image_pipeline,
)


class TestGetApiKey:
    def test_returns_none_if_no_file(self):
        with patch("core.zhipu_generator.ROOT", Path("/nonexistent")):
            key = get_zhipu_api_key()
            assert key is None

    def test_returns_key_from_config(self, tmp_path):
        models_json = tmp_path / "models.json"
        models_json.write_text(
            json.dumps({"providers": {"zhipu": {"api_key": "test-key-123"}}}),
            encoding="utf-8",
        )
        with patch("core.zhipu_generator.ROOT", tmp_path):
            key = get_zhipu_api_key()
            assert key == "test-key-123"

    def test_returns_none_if_no_zhipu_config(self, tmp_path):
        models_json = tmp_path / "models.json"
        models_json.write_text(
            json.dumps({"providers": {}}), encoding="utf-8"
        )
        with patch("core.zhipu_generator.ROOT", tmp_path):
            key = get_zhipu_api_key()
            assert key is None


class TestGenerateImage:
    def test_returns_error_without_key(self):
        with patch("core.zhipu_generator.get_zhipu_api_key", return_value=None):
            result = generate_image("a cat")
            assert result.get("status") == "error"

    def test_accepts_explicit_key(self):
        with patch("core.zhipu_generator.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "data": [{"url": "http://example.com/img.png"}]
            }
            result = generate_image("a cat", key="sk-test-key")
            assert "url" in result or "task_id" in result


class TestGenerateVideo:
    def test_returns_error_without_key(self):
        with patch("core.zhipu_generator.get_zhipu_api_key", return_value=None):
            result = generate_video("a beach")
            assert result.get("status") == "error"


class TestPollVideo:
    def test_returns_status(self):
        with patch("core.zhipu_generator.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "task_status": "PROCESSING"
            }
            result = poll_video("task-123", key="sk-test")
            assert isinstance(result, dict)


class TestImagePipeline:
    def test_returns_error_without_key(self):
        with patch("core.zhipu_generator.get_zhipu_api_key", return_value=None):
            result = zhipu_image_pipeline("a cat")
            assert result.get("status") == "error"

    def test_returns_pipeline_result(self):
        with patch("core.zhipu_generator.get_zhipu_api_key", return_value="sk-test"), \
             patch("core.zhipu_generator.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "data": [{"url": "http://example.com/img.png"}]
            }
            result = zhipu_image_pipeline("a cat")
            assert isinstance(result, dict)
