"""Test that DesktopControlProvider.type() handles special characters."""

from tools.desktop_control import DesktopControlProvider


def test_type_special_chars():
    """Special characters like !@#$ should type without error."""
    dc = DesktopControlProvider()
    text = "Hello from CRUX! $100 deposit @ 5% interest."
    dc.type(text)


def test_type_shift_chars():
    """All _SHIFT_CHARS characters should be typable."""
    dc = DesktopControlProvider()
    dc.type('~!@#$%^&*()_+{}|:"<>?')


def test_type_mixed_text():
    """Mixed normal + special + number text should work."""
    dc = DesktopControlProvider()
    dc.type("Test #1: price = $49.99 (save 20%!)")
