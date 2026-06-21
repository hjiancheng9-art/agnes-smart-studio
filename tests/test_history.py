"""Tests for utils.history — history record management."""

import json

import pytest


@pytest.fixture(autouse=True)
def isolate_history(tmp_path, monkeypatch):
    """Redirect HISTORY_FILE and HISTORY_JSONL to tmp_path."""
    import utils.history as h
    monkeypatch.setattr(h, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(h, "HISTORY_JSONL", tmp_path / "history.jsonl")
    yield


class TestLoadAndSave:
    """Basic load/save operations."""

    def test_empty_history(self):
        from utils.history import load_history
        assert load_history() == []

    def test_save_and_load(self):
        from utils.history import save_history, load_history
        records = [
            {"id": "1", "type": "image", "prompt": "cat", "model": "agnes-1.5-flash"},
        ]
        save_history(records)
        loaded = load_history()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "1"

    def test_migrate_legacy_json(self, tmp_path):
        """Legacy history.json should be migrated to JSONL."""
        import utils.history as h
        legacy = h.HISTORY_FILE
        legacy.write_text(json.dumps([
            {"id": "old1", "type": "image", "prompt": "legacy", "model": "agnes-1.5-flash"},
        ]), encoding="utf-8")
        from utils.history import load_history
        records = load_history()
        assert len(records) == 1
        assert records[0]["id"] == "old1"


class TestAddRecord:
    """Incremental record addition."""

    def test_add_returns_record(self):
        from utils.history import add_record
        entry = add_record("image", "a cute cat", "agnes-1.5-flash", {"url": "http://x.png"})
        assert entry["type"] == "image"
        assert entry["prompt"] == "a cute cat"
        assert "id" in entry

    def test_add_appends(self):
        from utils.history import add_record, load_history
        add_record("image", "cat", "agnes-1.5-flash", {})
        add_record("image", "dog", "agnes-1.5-flash", {})
        records = load_history()
        assert len(records) == 2

    def test_add_default_favorited(self):
        from utils.history import add_record
        entry = add_record("video", "sunset", "agnes-2.0-flash", {})
        assert entry.get("favorited") is False

    def test_add_with_favorited(self):
        from utils.history import add_record
        entry = add_record("image", "cat", "agnes-1.5-flash", {}, favorited=True)
        assert entry.get("favorited") is True

    def test_slims_heavy_fields(self):
        """Heavy fields like b64_json should be stripped from stored records."""
        from utils.history import add_record, load_history
        add_record("image", "cat", "agnes-1.5-flash", {
            "b64_json": "x" * 10000,
            "image": "y" * 5000,
            "local_path": "/output/images/test.png",
        })
        records = load_history()
        result = records[0]["result"]
        # b64_json should be stripped
        assert "b64_json" not in result
        assert "image" not in result
        # local_path should be kept (it's in the whitelist)
        assert result["local_path"] == "/output/images/test.png"


class TestDeleteRecord:
    """Record deletion."""

    def test_delete_existing(self):
        from utils.history import add_record, delete_record, load_history
        entry = add_record("image", "cat", "agnes-1.5-flash", {})
        rid = entry["id"]
        assert delete_record(rid) is True
        assert load_history() == []

    def test_delete_nonexistent(self):
        from utils.history import delete_record
        assert delete_record("nonexistent-id") is False


class TestToggleFavorite:
    """Favorite toggling."""

    def test_toggle_unfavorited(self):
        from utils.history import add_record, toggle_favorite
        entry = add_record("image", "cat", "agnes-1.5-flash", {})
        rid = entry["id"]
        result = toggle_favorite(rid)
        assert result is True  # now favorited

    def test_toggle_twice(self):
        from utils.history import add_record, toggle_favorite
        entry = add_record("image", "cat", "agnes-1.5-flash", {})
        rid = entry["id"]
        toggle_favorite(rid)  # → True
        result = toggle_favorite(rid)  # → False
        assert result is False

    def test_toggle_nonexistent(self):
        from utils.history import toggle_favorite
        assert toggle_favorite("nonexistent-id") is False


class TestGetFavorites:
    """Filter favorited records."""

    def test_empty_favorites(self):
        from utils.history import get_favorites
        assert get_favorites() == []

    def test_with_favorites(self):
        from utils.history import add_record, toggle_favorite, get_favorites
        e1 = add_record("image", "cat", "agnes-1.5-flash", {})
        add_record("image", "dog", "agnes-1.5-flash", {})
        toggle_favorite(e1["id"])
        favs = get_favorites()
        assert len(favs) == 1
        assert favs[0]["id"] == e1["id"]


class TestSearchRecords:
    """Search across history."""

    def test_search_empty(self):
        from utils.history import search_records
        assert search_records("cat") == []

    def test_search_finds_match(self):
        from utils.history import add_record, search_records
        add_record("image", "a cute cat sleeping", "agnes-1.5-flash", {})
        add_record("image", "a fast dog running", "agnes-1.5-flash", {})
        results = search_records("cat")
        assert len(results) == 1
        assert "cat" in results[0]["prompt"]

    def test_search_case_insensitive(self):
        from utils.history import add_record, search_records
        add_record("image", "Beautiful Sunset", "agnes-1.5-flash", {})
        results = search_records("sunset")
        assert len(results) == 1

    def test_search_no_match(self):
        from utils.history import add_record, search_records
        add_record("image", "cat", "agnes-1.5-flash", {})
        assert search_records("xyznonexistent") == []
