"""Tests for core.version — single source of truth for version info."""

from core.version import (
    VERSION,
    __version__,
    get_version_string,
    get_version_tuple,
    print_version,
)


class TestVersionConstants:
    """Test version constants and their relationships."""

    def test_version_is_string(self):
        assert isinstance(__version__, str)

    def test_version_matches(self):
        assert __version__ == VERSION

    def test_version_format(self):
        parts = __version__.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()


class TestGetVersionString:
    def test_returns_string(self):
        result = get_version_string()
        assert isinstance(result, str)
        assert result == __version__


class TestGetVersionTuple:
    def test_returns_three_ints(self):
        result = get_version_tuple()
        assert isinstance(result, tuple)
        assert len(result) == 3
        for v in result:
            assert isinstance(v, int)

    def test_values_match_string(self):
        expected = tuple(int(p) for p in __version__.split("."))
        assert get_version_tuple() == expected


class TestPrintVersion:
    def test_prints_to_stdout(self, capsys):
        print_version()
        captured = capsys.readouterr()
        assert __version__ in captured.out
        assert "Version:" in captured.out


class TestAll:
    def test_all_exports(self):
        import core.version as mod

        for name in mod.__all__:
            assert hasattr(mod, name)
