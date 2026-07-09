"""
TDD tests for Message Prefix System (ui/msg_prefix.py)
"""

from __future__ import annotations

from ui.msg_prefix import PREFIX_STYLES, MsgType, get_prefix


class TestMessagePrefix:
    def test_all_types_have_prefix(self):
        for msgt in MsgType:
            prefix = get_prefix(msgt.value, mode="compact")
            assert prefix, f"{msgt.value} should have a prefix"
            assert len(prefix.strip()) >= 2

    def test_compact_mode(self):
        assert get_prefix("user", mode="compact") == "[U] "
        assert get_prefix("assistant", mode="compact") == "[A] "
        assert get_prefix("system", mode="compact") == "[S] "
        assert get_prefix("error", mode="compact") == "[E] "
        assert get_prefix("success", mode="compact") == "[✓] "
        assert get_prefix("thinking", mode="compact") == "[T] "
        assert get_prefix("info", mode="compact") == "[·] "

    def test_label_mode(self):
        assert get_prefix("user", mode="label") == "[U] "
        assert get_prefix("error", mode="label") == "[E] "

    def test_symbol_mode(self):
        assert get_prefix("user", mode="symbol") == " ▸ "
        assert get_prefix("assistant", mode="symbol") == " ◆ "
        assert get_prefix("error", mode="symbol") == " ✕ "
        assert get_prefix("success", mode="symbol") == " ✓ "
        assert get_prefix("thinking", mode="symbol") == " … "

    def test_full_mode(self):
        prefix = get_prefix("user", mode="full")
        assert "用户消息" in prefix or "User" in prefix

    def test_unknown_type(self):
        assert get_prefix("unknown", mode="compact") == ""
        assert get_prefix("", mode="compact") == ""

    def test_prefix_styles_exist(self):
        for key in ["msg-user", "msg-assistant", "msg-system", "msg-error", "msg-success", "msg-thinking", "msg-info"]:
            assert key in PREFIX_STYLES

    def test_all_prefixes_unique(self):
        """Each message type should have a unique compact prefix."""
        seen = set()
        for msgt in MsgType:
            p = get_prefix(msgt.value, mode="compact")
            assert p not in seen, f"Duplicate prefix: {p}"
            seen.add(p)
