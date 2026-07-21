"""Tests for core/bootstrap.py — startup health check and output helpers."""

from __future__ import annotations

from core.bootstrap import print_kimi_tree, run_startup_health, safe_rich_print


class TestSafeRichPrint:
    """safe_rich_print() returns a callable that works with/without Rich."""

    def test_returns_callable(self):
        rp = safe_rich_print()
        assert callable(rp)

    def test_plain_print_does_not_crash(self, capsys):
        rp = safe_rich_print()
        rp("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_print_with_kwargs(self, capsys):
        rp = safe_rich_print()
        rp("hello", end="!")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_print_empty(self, capsys):
        rp = safe_rich_print()
        rp()
        captured = capsys.readouterr()
        # Should print nothing (or newline)
        assert captured.out in ("", "\n", "\r\n")


class TestPrintKimiTree:
    """print_kimi_tree() renders a directory tree safely."""

    def test_prints_top_level(self, capsys, tmp_path):
        (tmp_path / "file1.py").write_text("")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("")
        print_kimi_tree(tmp_path, max_depth=1)
        captured = capsys.readouterr()
        assert "file1.py" in captured.out
        # max_depth=1 should not show nested content in subdir
        # but the function might show subdir itself

    def test_max_depth_respected(self, capsys, tmp_path):
        d1 = tmp_path / "d1"
        d2 = d1 / "d2"
        d2.mkdir(parents=True)
        (d2 / "deep.txt").write_text("")
        print_kimi_tree(tmp_path, max_depth=1)
        captured = capsys.readouterr()
        # deep.txt should not appear at depth 1
        assert "deep.txt" not in captured.out

    def test_empty_directory(self, capsys, tmp_path):
        empty_dir = tmp_path / "empty_subdir"
        empty_dir.mkdir()
        print_kimi_tree(empty_dir)
        captured = capsys.readouterr()
        # Should not crash on empty dir
        assert isinstance(captured.out, str)

    def test_hidden_directories_censored(self, capsys, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.py").write_text("")
        (tmp_path / "visible.py").write_text("")
        print_kimi_tree(tmp_path, max_depth=2)
        captured = capsys.readouterr()
        assert "visible.py" in captured.out
        # Hidden dir may be censored or marked
        assert "secret.py" not in captured.out


class TestRunStartupHealth:
    """run_startup_health() — silent health check before REPL."""

    def test_runs_without_error(self):
        # Should not raise any exception
        run_startup_health()

    def test_no_output_to_stdout(self, capsys):
        run_startup_health()
        captured = capsys.readouterr()
        # Should be silent (logs only, not stdout)
        assert captured.out == ""
        assert captured.err == ""
