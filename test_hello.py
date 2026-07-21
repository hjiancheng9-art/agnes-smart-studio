"""Tests for hello_world function."""

from hello import hello_world


def test_hello_world() -> None:
    """hello_world should return the classic greeting."""
    result = hello_world()
    assert result == "Hello, World!"
