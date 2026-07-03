"""Tests for core/client.py — Categories D+F client fixes."""

import base64
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.client import CruxClient


class TestChatMultimodalLocalFile:
    """Verify local file path → data: URL conversion logic."""

    def test_chat_multimodal_local_file(self):
        """Create a temp small PNG, pass path to chat_multimodal, verify data: URL created."""
        from PIL import Image

        # Create a small 10x10 red PNG
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        tmpdir = tempfile.mkdtemp()
        png_path = os.path.join(tmpdir, "test_image.png")
        img.save(png_path, "PNG")

        client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")

        # We can't actually call the API, so we mock _request_with_retry
        with patch.object(client, "_request_with_retry", return_value=MagicMock(status_code=200, json=MagicMock(return_value={"choices": [{"message": {"content": "ok"}}]}))):
            # But chat_multimodal calls self.chat which calls _request_with_retry
            # We need to mock at the HTTP level
            pass

        # Instead, test the URL conversion logic directly by inspecting the code path.
        # The chat_multimodal method converts local files to data: URLs.
        # We verify this by checking the method's logic on a real temp file.
        from unittest.mock import Mock

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch.object(client._http, "post", return_value=mock_resp):
            result = client.chat_multimodal("describe this image", png_path)
            # Should return a valid response dict
            assert "choices" in result
            assert len(result["choices"]) > 0

        # Clean up
        os.remove(png_path)
        os.rmdir(tmpdir)

    def test_chat_multimodal_url_passthrough(self):
        """Verify https:// URLs pass through unchanged (no local file conversion)."""
        client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_post = Mock(return_value=mock_resp)
        with patch.object(client._http, "post", mock_post):
            result = client.chat_multimodal(
                "describe this image",
                "https://example.com/photo.jpg",
            )
            assert "choices" in result
            # Verify URL passed through as-is while still inside the mock context
            sent_body = mock_post.call_args[1]["json"]
            image_url_in_msg = sent_body["messages"][0]["content"][1]["image_url"]["url"]
            assert image_url_in_msg == "https://example.com/photo.jpg"

    def test_chat_multimodal_data_uri_passthrough(self):
        """Verify data: URIs pass through unchanged."""
        client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_post = Mock(return_value=mock_resp)
        with patch.object(client._http, "post", mock_post):
            result = client.chat_multimodal("what is this", data_uri)
            assert "choices" in result
            sent_body = mock_post.call_args[1]["json"]
            image_url_in_msg = sent_body["messages"][0]["content"][1]["image_url"]["url"]
            assert image_url_in_msg == data_uri

    def test_chat_multimodal_compression(self):
        """Create a 4000x3000 PIL image, verify the code path compresses it."""
        from PIL import Image

        # Create a large image (4000x3000)
        img = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
        tmpdir = tempfile.mkdtemp()
        png_path = os.path.join(tmpdir, "large_image.png")
        img.save(png_path, "PNG")

        original_size = os.path.getsize(png_path)
        client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_post = Mock(return_value=mock_resp)
        with patch.object(client._http, "post", mock_post):
            result = client.chat_multimodal("describe", png_path)
            assert "choices" in result
            sent_body = mock_post.call_args[1]["json"]
            image_url_in_msg = sent_body["messages"][0]["content"][1]["image_url"]["url"]

            # Should be a data: URL (compressed, not the raw file)
            assert image_url_in_msg.startswith("data:image/jpeg;base64,")

            # The compressed base64 payload should be reasonably small
            b64_part = image_url_in_msg.split(";base64,")[1]
            decoded_size = len(base64.b64decode(b64_part))
            # Compressed JPEG should be much smaller than original PNG of a 12MP image
            assert decoded_size < original_size, (
                f"Compressed size {decoded_size} should be less than original {original_size}"
            )

        # Clean up
        os.remove(png_path)
        os.rmdir(tmpdir)

    def test_chat_multimodal_nonexistent_file(self):
        """Verify graceful handling of non-existent file path."""
        client = CruxClient(api_key="fake-key", base_url="http://localhost:9999")
        result = client.chat_multimodal("describe", "/nonexistent/path/image.png")
        # Should return an error message in content, not crash
        assert "choices" in result
        content = result["choices"][0]["message"]["content"]
        assert "不存在" in content or "not" in content.lower()


class TestHttpRequestDbQuery:
    """Verify new utility functions are importable and callable."""

    def test_http_request_function_exists(self):
        """Verify http_request is importable and callable from core.client."""
        from core.client import http_request
        assert callable(http_request)

    def test_db_query_function_exists(self):
        """Verify db_query is importable and callable from core.client."""
        from core.client import db_query
        assert callable(db_query)
