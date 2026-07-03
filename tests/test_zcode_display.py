"""Test ui/display.py helpers — view image, tool search, plan update."""

from __future__ import annotations

import json

import pytest

from ui.display import _view_image, _tool_search, _update_plan


class TestViewImage:
    def test_view_image_missing_file(self):
        """_view_image with nonexistent path returns JSON with 'error' key."""
        result = _view_image("/nonexistent/path.png")
        data = json.loads(result)
        assert "error" in data, f"Expected 'error' key, got: {data}"


class TestToolSearch:
    def test_tool_search_finds_match(self):
        """_tool_search('read_file') returns JSON containing 'read_file'."""
        result = _tool_search("read_file")
        assert "read_file" in result, f"Expected 'read_file' in result: {result[:200]}"

    def test_tool_search_no_match(self):
        """_tool_search('xyznonexistent123') returns JSON with empty matches."""
        result = _tool_search("xyznonexistent123")
        data = json.loads(result)
        assert data.get("matches") == [], f"Expected empty matches, got: {data}"


class TestUpdatePlan:
    def test_update_plan_returns_json(self):
        """_update_plan(action='add', name='test') returns valid JSON string."""
        result = _update_plan(action="add", name="test")
        data = json.loads(result)
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        # Either "status": "ok" or a note about plan mode not active
        assert "status" in data or "error" in data, f"Unexpected response: {data}"
