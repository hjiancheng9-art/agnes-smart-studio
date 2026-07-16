"""Tests for completer.py — command/file/history completion."""

from unittest.mock import MagicMock

import pytest

from ui.completer import COMMANDS, TuiCompleter


class TestCommands:
    """COMMANDS list is well-formed."""

    def test_not_empty(self):
        assert len(COMMANDS) > 0

    def test_all_tuples(self):
        assert all(isinstance(c, tuple) for c in COMMANDS)

    def test_each_has_name_and_desc(self):
        for c in COMMANDS:
            assert len(c) >= 2

    def test_no_duplicate_names(self):
        names = [c[0] for c in COMMANDS]
        assert len(names) == len(set(names))


class TestTuiCompleter:
    """TuiCompleter provides intelligent completion."""

    @pytest.fixture
    def completer(self):
        return TuiCompleter()

    @pytest.fixture
    def mock_doc(self):
        """Mock Document with text_before_cursor."""
        doc = MagicMock()
        doc.text_before_cursor = ""
        return doc

    def test_creation(self, completer):
        assert completer is not None

    def test_empty_input(self, completer, mock_doc):
        mock_doc.text_before_cursor = ""
        results = list(completer.get_completions(mock_doc, ""))
        assert isinstance(results, list)

    def test_partial_input(self, completer, mock_doc):
        mock_doc.text_before_cursor = "he"
        results = list(completer.get_completions(mock_doc, "he"))
        assert isinstance(results, list)

    def test_slash_input(self, completer, mock_doc):
        mock_doc.text_before_cursor = "/"
        results = list(completer.get_completions(mock_doc, "/"))
        assert isinstance(results, list)

    def test_completion_has_text(self, completer, mock_doc):
        mock_doc.text_before_cursor = "a"
        results = list(completer.get_completions(mock_doc, "a"))
        if results:
            for r in results:
                assert hasattr(r, "text")
