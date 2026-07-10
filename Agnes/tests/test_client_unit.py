# -*- coding: utf-8 -*-
"""Unit tests for AgnesClient – no live API calls."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agnes.client import AgnesClient, AgnesConfig, AgnesError


@pytest.fixture
def mock_client():
    """Create a client with a fake key for unit testing."""
    cfg = AgnesConfig(api_key="sk-test-mock")
    return AgnesClient(config=cfg)


class TestClientInit:
    def test_init_without_key_raises(self):
        old = os.environ.pop("AGNES_API_KEY", None)
        try:
            with pytest.raises(AgnesError, match="API Key"):
                AgnesClient()
        finally:
            if old:
                os.environ["AGNES_API_KEY"] = old

    def test_init_with_explicit_config(self):
        cfg = AgnesConfig(api_key="sk-explicit")
        c = AgnesClient(config=cfg)
        assert c.config.api_key == "sk-explicit"
        assert c._headers["Authorization"] == "Bearer sk-explicit"

    def test_init_sets_headers(self, mock_client):
        assert "Authorization" in mock_client._headers
        assert mock_client._headers["Content-Type"] == "application/json"


class TestRequest:
    def test_non_2xx_raises(self, mock_client):
        with patch("agnes.client.requests.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.json.return_value = {"message": "Invalid key"}
            mock_resp.text = '{"message": "Invalid key"}'
            mock_req.return_value = mock_resp
            with pytest.raises(AgnesError, match="401"):
                mock_client._request("GET", "/test")

    def test_2xx_returns_json(self, mock_client):
        with patch("agnes.client.requests.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": [{"id": "m1"}]}
            mock_req.return_value = mock_resp
            result = mock_client._request("GET", "/models")
            assert result == {"data": [{"id": "m1"}]}

    def test_adds_timeout_default(self, mock_client):
        with patch("agnes.client.requests.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {}
            mock_req.return_value = mock_resp
            mock_client._request("POST", "/chat/completions")
            assert "timeout" in mock_req.call_args[1]


class TestChat:
    def test_chat_returns_response(self, mock_client):
        with patch.object(mock_client, "_request") as mock_req:
            mock_req.return_value = {
                "choices": [{"message": {"content": "Hello"}}]
            }
            resp = mock_client.chat([{"role": "user", "content": "hi"}])
            assert resp["choices"][0]["message"]["content"] == "Hello"

    def test_chat_text_strips(self, mock_client):
        with patch.object(mock_client, "_request") as mock_req:
            mock_req.return_value = {
                "choices": [{"message": {"content": "Hi there"}}]
            }
            reply = mock_client.chat_text("hello")
            assert reply == "Hi there"

    def test_chat_stream_returns_generator(self, mock_client):
        with patch("agnes.client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = [
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                b"data: [DONE]",
            ]
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            gen = mock_client.chat(
                [{"role": "user", "content": "hi"}], stream=True
            )
            chunks = list(gen)
            assert len(chunks) >= 1
            assert "Hello" in "".join(chunks)

    def test_chat_with_image(self, mock_client):
        with patch.object(mock_client, "_request") as mock_req:
            mock_req.return_value = {
                "choices": [{"message": {"content": "cat"}}]
            }
            mock_client.chat_with_image("what?", "http://x.com/i.jpg")
            sent = mock_req.call_args[1]["json"]["messages"]
            content = sent[0]["content"]
            assert isinstance(content, list)
            assert content[1]["type"] == "image_url"


class TestImageGen:
    def test_generate_image_returns_list(self, mock_client):
        with patch.object(mock_client, "_request") as mock_req:
            mock_req.return_value = {
                "data": [{
                    "url": "http://x.com/i.png",
                    "b64_json": "",
                    "revised_prompt": "a circle",
                }]
            }
            result = mock_client.generate_image("a circle")
            assert isinstance(result, list)
            assert result[0]["url"] == "http://x.com/i.png"

    def test_generate_image_and_save(self, mock_client, tmp_path):
        save = str(tmp_path / "t.png")
        with patch.object(mock_client, "generate_image") as mg, \
             patch.object(mock_client, "download_file") as md:
            mg.return_value = [{
                "url": "http://x.com/i.png",
                "b64_json": "",
                "revised_prompt": "",
            }]
            md.return_value = save
            result = mock_client.generate_image_and_save("test", save_path=save)
            assert result == save


class TestModels:
    def test_list_models(self, mock_client):
        with patch.object(mock_client, "_request") as mock_req:
            mock_req.return_value = {"data": [{"id": "m1"}, {"id": "m2"}]}
            models = mock_client.list_models()
            assert isinstance(models, list)
            assert len(models) == 2

    def test_get_model_type(self):
        assert AgnesClient.get_model_type("agnes-2.0-flash") == "chat"
        assert AgnesClient.get_model_type("agnes-image-2.0-flash") == "image"
        assert AgnesClient.get_model_type("agnes-video-v2.0") == "video"
        assert AgnesClient.get_model_type("unknown-model") == "unknown"


class TestUtils:
    def test_download_file(self, mock_client, tmp_path):
        save = str(tmp_path / "dl.png")
        with patch("agnes.client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"fake-png-data"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            result = mock_client.download_file("http://x.com/i.png", save)
            assert os.path.exists(result)
            with open(result, "rb") as f:
                assert f.read() == b"fake-png-data"

    def test_image_to_base64(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        uri = AgnesClient.image_to_base64(str(img))
        assert uri.startswith("data:image/png;base64,")

    def test_validate_size_valid(self, mock_client):
        # _validate_size returns None on success (validates only)
        mock_client._validate_size("1024x768")  # no exception
        mock_client._validate_size("1152x864")  # no exception

    def test_validate_size_invalid(self, mock_client):
        from agnes.client import AgnesError
        with pytest.raises((ValueError, AgnesError)):
            mock_client._validate_size("100x100")
        with pytest.raises((ValueError, AgnesError)):
            mock_client._validate_size("abc")
