"""Tests for ui/beautify.py — dividers, panels, input helpers."""

from ui.beautify import (
    hr,
    hr_heavy,
    hr_dot,
    section_header,
    info_panel,
    success_panel,
    error_panel,
    warn_panel,
    input_prompt_line,
)


class TestDividers:
    def test_hr_does_not_raise(self):
        hr()

    def test_hr_with_custom_params(self):
        hr(char="=", length=20, color="red")

    def test_hr_heavy_does_not_raise(self):
        hr_heavy("Section")

    def test_hr_dot_does_not_raise(self):
        hr_dot()


class TestSectionHeader:
    def test_does_not_raise(self):
        section_header("Test Header")  # prints to console, returns None


class TestPanels:
    def test_info_panel_does_not_raise(self):
        info_panel("info message")

    def test_success_panel_does_not_raise(self):
        success_panel("success message")

    def test_error_panel_does_not_raise(self):
        error_panel("error message")

    def test_warn_panel_does_not_raise(self):
        warn_panel("warning message")


class TestInputPrompt:
    def test_returns_string(self):
        result = input_prompt_line("Enter: ")
        assert isinstance(result, str)
