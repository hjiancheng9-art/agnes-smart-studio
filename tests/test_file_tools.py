"""Tests for core.file_tools — file ops, path sandboxing, SSRF protection.

These are the most-used utility functions in the agent. Security-critical:
_safe_path prevents sandbox escapes, _validate_url prevents SSRF.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def in_project(tmp_path, monkeypatch):
    """Create a fake project structure and chdir into it."""
    (tmp_path / "test_dir").mkdir()
    (tmp_path / "test_dir" / "file1.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "test_dir" / "file2.md").write_text("# Title\n\nContent here\n", encoding="utf-8")
    (tmp_path / "test_dir" / "subdir").mkdir()
    (tmp_path / "test_dir" / "subdir" / "nested.py").write_text("x = 42\n", encoding="utf-8")
    (tmp_path / "big_file.txt").write_text("\n".join(f"line {i}" for i in range(600)), encoding="utf-8")
    return tmp_path


# ── _safe_path — sandbox enforcement ─────────────────────────────────────


class TestSafePath:
    """Path resolution with project-root containment enforcement."""

    def test_path_within_root_ok(self, in_project):
        from core.file_tools import ROOT, _safe_path

        # Use the actual project root
        p = _safe_path(str(ROOT / "core" / "file_tools.py"))
        assert p.exists()

    def test_path_outside_root_rejected(self, in_project):
        from core.file_tools import _safe_path

        # /etc/passwd is definitely outside project root
        with pytest.raises(ValueError, match="超出项目根目录"):
            _safe_path("/etc/passwd")

    def test_path_with_dotdot_rejected(self, in_project):
        from core.file_tools import ROOT, _safe_path

        # Try to escape via ../../
        escape = str(ROOT / "core" / ".." / ".." / ".." / "etc" / "passwd")
        with pytest.raises(ValueError, match="超出项目根目录"):
            _safe_path(escape)

    def test_relative_path_resolved(self, in_project):
        from core.file_tools import ROOT, _safe_path

        # Relative path should resolve against cwd (which is project root in tests)
        p = _safe_path("core/file_tools.py")
        assert p == (ROOT / "core" / "file_tools.py").resolve()


# ── read_file ────────────────────────────────────────────────────────────


class TestReadFile:
    """File reading with offset/limit and truncation."""

    def test_read_existing_file(self, in_project):
        from core.file_tools import read_file

        # Read a known file within project root
        result = read_file("core/version.py")
        assert "version" in result.lower() or "__version__" in result

    def test_read_nonexistent_file(self, in_project):
        from core.file_tools import read_file

        result = read_file("nonexistent_file_xyz.py")
        assert "不存在" in result or "错误" in result

    def test_read_outside_root_allowed(self, in_project):
        from core.file_tools import read_file

        # read_file now allows reading any path; /etc/passwd won't exist on
        # Windows so we expect "文件不存在" rather than "安全拒绝".
        result = read_file("/etc/passwd")
        assert "安全拒绝" not in result  # path restriction is lifted for reads

    def test_read_with_offset(self, in_project):
        from core.file_tools import read_file

        result = read_file("core/version.py", offset=2)
        # Should skip first 2 lines
        assert isinstance(result, str)
        assert "lines 3-" in result  # header shows offset

    def test_read_with_limit(self, in_project):
        from core.file_tools import read_file

        result = read_file("core/version.py", limit=3)
        assert isinstance(result, str)

    def test_large_file_truncated(self, in_project):
        from core.file_tools import ROOT, read_file

        # Create a file with >500 lines in project root
        big = ROOT / "_test_big.txt"
        try:
            big.write_text("\n".join(f"line {i}" for i in range(600)), encoding="utf-8")
            result = read_file("_test_big.txt")
            assert "first 500 of 600" in result or "truncated" in result.lower() or "of 600" in result
        finally:
            big.unlink(missing_ok=True)


# ── write_file ───────────────────────────────────────────────────────────


class TestWriteFile:
    """File writing with UTF-8 encoding."""

    def test_write_new_file(self, in_project):
        from core.file_tools import ROOT, write_file

        path = "output/_test_write_tmp.txt"
        result = write_file(path, "hello world\n中文内容")
        assert "Written" in result
        assert (ROOT / path).read_text(encoding="utf-8") == "hello world\n中文内容"

    def test_write_overwrites_existing(self, in_project):
        from core.file_tools import ROOT, write_file

        path = "output/_test_overwrite.txt"
        write_file(path, "original")
        write_file(path, "replaced")
        assert (ROOT / path).read_text(encoding="utf-8") == "replaced"

    def test_write_outside_root_rejected(self, in_project):
        from core.file_tools import write_file

        with pytest.raises(ValueError, match="超出项目根目录"):
            write_file("/etc/test_agnes_write", "bad")

    def test_write_creates_parent_dirs(self, in_project):
        from core.file_tools import ROOT, write_file

        path = "output/_nested/deep/dir/file.txt"
        result = write_file(path, "nested content")
        assert "Written" in result
        assert (ROOT / path).exists()


# ── search_files ─────────────────────────────────────────────────────────


class TestSearchFiles:
    """Regex search across project files."""

    def test_search_finds_pattern(self, in_project):
        from core.file_tools import search_files

        result = search_files("class CommandDef")
        # Should find it in core/commands.py
        assert isinstance(result, str)
        assert len(result) > 0

    def test_search_no_matches(self, in_project):
        from core.file_tools import search_files

        result = search_files("zzz_no_such_pattern_xyzzy_12345")
        assert isinstance(result, str)

    def test_search_invalid_regex(self, in_project):
        from core.file_tools import search_files

        result = search_files("[invalid regex")
        assert isinstance(result, str)
        # Should return error message, not crash


# ── list_files ───────────────────────────────────────────────────────────


class TestListFiles:
    """Directory listing with sizes."""

    def test_list_current_dir(self, in_project):
        from core.file_tools import list_files

        result = list_files(".")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should list core/ and ui/ etc
        assert "core" in result

    def test_list_core_dir(self, in_project):
        from core.file_tools import list_files

        result = list_files("core")
        # core/ has 70+ files, truncated at 50; just verify it returns content
        assert isinstance(result, str)
        assert ".py" in result or "/" in result

    def test_list_nonexistent_dir(self, in_project):
        from core.file_tools import list_files

        result = list_files("no_such_directory_xyz")
        assert "不存在" in result or "错误" in result


# ── _validate_url — SSRF protection ──────────────────────────────────────


class TestValidateUrl:
    """SSRF prevention — block internal addresses."""

    def test_valid_https_url(self):
        from core.file_tools import _validate_url

        assert _validate_url("https://example.com/page") is None

    def test_valid_http_url(self):
        from core.file_tools import _validate_url

        assert _validate_url("http://example.com") is None

    def test_localhost_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://localhost:8080")
        assert result is not None
        assert "localhost" in result

    def test_127_0_0_1_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://127.0.0.1/")
        assert result is not None
        assert "127.0.0.1" in result

    def test_aws_metadata_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://169.254.169.254/latest/meta-data/")
        assert result is not None
        assert "内部" in result

    def test_gcp_metadata_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://metadata.google.internal/computeMetadata/")
        assert result is not None

    def test_private_network_10_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://10.0.0.1/")
        assert result is not None
        assert "内部" in result

    def test_private_network_192_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://192.168.1.1/")
        assert result is not None

    def test_private_network_172_blocked(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://172.16.0.1/")
        assert result is not None

    def test_invalid_scheme_rejected(self):
        from core.file_tools import _validate_url

        result = _validate_url("ftp://example.com/file")
        assert result is not None
        assert "协议" in result

    def test_file_scheme_rejected(self):
        from core.file_tools import _validate_url

        result = _validate_url("file:///etc/passwd")
        assert result is not None

    def test_no_hostname_rejected(self):
        from core.file_tools import _validate_url

        result = _validate_url("http://")
        assert result is not None
        assert "主机名" in result


# ── pip_install — whitelist enforcement ──────────────────────────────────


class TestPipInstall:
    """Package installation with whitelist safety."""

    def test_rejected_package(self):
        from core.file_tools import pip_install

        result = pip_install("malicious-package-xyz")
        assert "安全拒绝" in result or "白名单" in result

    def test_empty_package_rejected(self):
        from core.file_tools import pip_install

        result = pip_install("")
        assert "错误" in result

    def test_safe_package_format(self):
        from core.file_tools import pip_install

        # pytest is in the whitelist — mock subprocess to avoid real install
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
            result = pip_install("pytest")
            # Should not be rejected by whitelist
            assert "安全拒绝" not in result


# ── glob_files ───────────────────────────────────────────────────────────


class TestGlobFiles:
    """Glob pattern file matching."""

    def test_glob_python_files(self):
        from core.file_tools import glob_files

        result = glob_files("core/*.py")
        assert isinstance(result, str)
        assert ".py" in result

    def test_glob_no_matches(self):
        from core.file_tools import glob_files

        result = glob_files("*.zzz_nonexistent")
        assert isinstance(result, str)


# ── count_lines ──────────────────────────────────────────────────────────


class TestCountLines:
    """Project line counter."""

    def test_count_returns_string(self):
        from core.file_tools import count_lines

        result = count_lines()
        assert isinstance(result, str)
        assert len(result) > 0
        # Should mention python or lines
        assert "py" in result.lower() or "line" in result.lower()


# ── tree_dir ─────────────────────────────────────────────────────────────


class TestTreeDir:
    """Directory tree visualization."""

    def test_tree_default_depth(self):
        from core.file_tools import tree_dir

        result = tree_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tree_shallow_depth(self):
        from core.file_tools import tree_dir

        result = tree_dir(depth=1)
        assert isinstance(result, str)


# ── think_deep — 本地重型推理 ────────────────────────────────────────────


class TestThinkDeep:
    """think_deep 调用 llama-server（本地 :8080），用 httpx mock 测试各路径。"""

    def test_returns_content_on_success(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        from core.file_tools import think_deep

        _mock_client = MagicMock()
        # /v1/models probe
        mock_probe = MagicMock()
        mock_probe.status_code = 200
        mock_probe.json.return_value = {"models": [{"name": "qwen2.5-coder-7b"}]}
        # /v1/chat/completions
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "推理结果：这里是LLM的深度分析输出。"}}]}

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, **kw):
                return mock_probe

            def post(self, url, **kw):
                return mock_resp

        with patch("core.file_tools.httpx.Client", FakeClient):
            result = think_deep("请分析这段代码的性能瓶颈")
            assert "推理结果" in result
            assert "深度分析" in result

    def test_returns_error_on_http_failure(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        from core.file_tools import think_deep

        mock_probe = MagicMock()
        mock_probe.status_code = 200
        mock_probe.json.return_value = {"models": [{"name": "local-model"}]}

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.json.return_value = {"error": {"message": "model overloaded"}}

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, **kw):
                return mock_probe

            def post(self, url, **kw):
                return mock_resp

        with patch("core.file_tools.httpx.Client", FakeClient):
            result = think_deep("hello")
            assert "error" in result.lower() or "model" in result.lower() or "500" in result

    def test_returns_not_connected_on_connect_error(self, monkeypatch):
        from unittest.mock import patch

        import httpx as real_httpx

        from core.file_tools import think_deep

        class FailingClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, **kw):
                raise real_httpx.ConnectError("connection refused")

            def post(self, url, **kw):
                raise real_httpx.ConnectError("connection refused")

        with patch("core.file_tools.httpx.Client", FailingClient):
            result = think_deep("test")
            assert "not connected" in result.lower() or "connect" in result.lower()

    def test_respects_max_tokens_parameter(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        from core.file_tools import think_deep

        mock_probe = MagicMock()
        mock_probe.status_code = 200
        mock_probe.json.return_value = {"models": [{"name": "test-model"}]}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        captured_post_kwargs = {}

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, **kw):
                return mock_probe

            def post(self, url, **kw):
                captured_post_kwargs.update(kw)
                return mock_resp

        with patch("core.file_tools.httpx.Client", FakeClient):
            think_deep("test", max_tokens=500)
            body = captured_post_kwargs.get("json", {})
            assert body.get("max_tokens") == 500

    def test_probe_failure_falls_back_to_default_model(self, monkeypatch):
        """llama-server probe 失败时用 'local-model' 作为默认 model_id。"""
        from unittest.mock import MagicMock, patch

        from core.file_tools import think_deep

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "fallback ok"}}]}

        captured_post_json = {}

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, **kw):
                # probe fails
                raise TimeoutError("probe timeout")

            def post(self, url, **kw):
                captured_post_json.update(kw.get("json", {}))
                return mock_resp

        with patch("core.file_tools.httpx.Client", FakeClient):
            result = think_deep("test prompt")
            assert result == "fallback ok"
            assert captured_post_json.get("model") == "local-model"
