"""Tests for core/image_tools.py"""

from core.image_tools import IMAGE_EXECUTOR_MAP, IMAGE_TOOL_DEFS


class TestImageTools:
    def test_executor_map(self):
        assert isinstance(IMAGE_EXECUTOR_MAP, dict)

    def test_tool_defs(self):
        assert isinstance(IMAGE_TOOL_DEFS, list)
