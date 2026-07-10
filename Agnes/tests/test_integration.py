# -*- coding: utf-8 -*-
"""Integration tests – requires live API (run: pytest -m integration)."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.integration


class TestLiveAPI:
    def test_list_models(self, client):
        models = client.list_models()
        assert len(models) >= 3
        ids = [m["id"] for m in models]
        assert any("agnes" in mid for mid in ids)

    def test_chat_text(self, client):
        reply = client.chat_text("回复：OK")
        assert len(reply.strip()) > 0

    def test_chat_math(self, client):
        reply = client.chat_text("1+1等于几？只回复数字")
        assert "2" in reply

    def test_chat_stream(self, client):
        gen = client.chat(
            [{"role": "user", "content": "从1数到3用顿号分隔"}],
            stream=True, max_tokens=50,
        )
        chunks = list(gen)
        assert len(chunks) >= 1
        assert len("".join(chunks)) > 0

    def test_generate_image(self, client):
        images = client.generate_image(
            "red dot on white", size="1024x768",
            model="agnes-image-2.1-flash",
        )
        assert isinstance(images, list)
        assert len(images) >= 1
        assert "url" in images[0] or "b64_json" in images[0]

    def test_generate_image_and_save(self, client, tmp_path):
        save = str(tmp_path / "itest.png")
        result = client.generate_image_and_save(
            "blue square", save_path=save,
            model="agnes-image-2.1-flash", size="1024x768",
        )
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000

    def test_download_file(self, client, tmp_path):
        images = client.generate_image(
            "green dot", size="1024x768",
            model="agnes-image-2.1-flash",
        )
        url = images[0].get("url", "")
        if not url:
            pytest.skip("No image URL")
        save = str(tmp_path / "dl.png")
        result = client.download_file(url, save)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 100

    def test_get_model_info(self, client):
        info = client.get_model_info("agnes-2.0-flash")
        assert info is not None
