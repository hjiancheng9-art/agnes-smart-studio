"""Tests for root tools.py — _view_image, _update_plan, _tool_search, _mcp_*, _request_user_input."""

import sys
from unittest.mock import patch

from tools import (
    _mcp_list_resources,
    _mcp_read_resource,
    _request_user_input,
    _tool_search,
    _update_plan,
    _view_image,
)


class TestToolSearch:
    def test_finds_image_tools(self):
        result = _tool_search("image")
        assert "imagegen" in result or "view_image" in result

    def test_no_match(self):
        result = _tool_search("zzz_nonexistent_xyz")
        assert "No tools found" in result


class TestUpdatePlan:
    def test_add(self):
        result = _update_plan(action="add", name="step1", tool="read_file", reason="test")
        assert "added step 0" in result

    def test_modify(self):
        _update_plan(action="add", name="orig", tool="run_bash")
        result = _update_plan(action="modify", step_id=0, name="changed", tool="run_python")
        assert "modified step 0" in result

    def test_remove(self):
        _update_plan(action="add", name="tmp", tool="read_file")
        result = _update_plan(action="remove", step_id=0)
        assert "removed step 0" in result

    def test_insert(self):
        _update_plan(action="add", name="first", tool="a")
        result = _update_plan(action="insert", step_id=0, name="inserted", tool="b")
        assert "inserted step 0" in result

    def test_invalid(self):
        result = _update_plan(action="bogus", step_id=999)
        assert "Invalid" in result


class TestViewImage:
    def test_nonexistent(self):
        result = _view_image("/nonexistent/img.png")
        assert "not found" in result

    @patch("sys.platform", "linux")
    @patch("subprocess.Popen")
    def test_linux_opens(self, mock_popen):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", return_value="/tmp/test.png"):
            result = _view_image("/tmp/test.png")
            assert "Opened" in result


class TestMcpTools:
    def test_list_no_connection(self):
        result = _mcp_list_resources()
        assert "No MCP servers" in result or "MCP client" in result

    def test_read_no_connection(self):
        result = _mcp_read_resource("file:///test")
        assert "No MCP servers" in result or "MCP client" in result


class TestRequestUserInput:
    @patch("builtins.input", return_value="yes")
    def test_returns_input(self, mock_input):
        result = _request_user_input("Continue?")
        assert result == "yes"

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_cancels(self, mock_input):
        result = _request_user_input("Question?")
        assert "cancelled" in result
