"""Unit tests for core/github_tools.py — GitHub 工具集（基于 gh CLI）。

所有测试通过 monkeypatch _run_gh 为假实现，不触达真实 gh CLI。
断言：
- _parse_repo_arg 的 URL → slug 转换
- 各 execute_* 函数的参数拼接与错误处理
- 返回值的 JSON 格式
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.github_tools import (
    _parse_repo_arg,
    _run_gh,
    execute_github_api,
    execute_github_browse,
    execute_github_issue,
    execute_github_pr,
    execute_github_readme,
    execute_github_release,
    execute_github_repo_list,
    execute_github_repo_view,
    execute_github_search,
    execute_github_write_file,
)


# ── 辅助：可编程 mock _run_gh ──────────────────────────────────────


class FakeGh:
    """可编程的 _run_gh 替身：按 args 关键词或 callable 返回预设结果，记录调用参数。

    returns 支持:
      - str key: 检查 args 列表中是否包含该字符串
      - callable: 传入 args，返回 True 时使用对应 value
    """

    def __init__(self, returns=None, default=None):
        self.returns = returns or {}
        self.default = default or {"success": True, "stdout": "", "stderr": ""}
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout=30):
        self.calls.append(args)
        for key, val in self.returns.items():
            if callable(key):
                if key(args):
                    return val
            elif key in args:
                return val
        return self.default


@pytest.fixture
def fake_gh():
    """一个默认返回空的 FakeGh 实例。"""
    return FakeGh()


# ── _parse_repo_arg ────────────────────────────────────────────────


class TestParseRepoArg:
    """_parse_repo_arg URL → owner/repo 转换。"""

    def test_owner_slash_repo_passthrough(self):
        assert _parse_repo_arg("torvalds/linux") == "torvalds/linux"

    def test_https_url(self):
        assert _parse_repo_arg("https://github.com/torvalds/linux") == "torvalds/linux"

    def test_https_url_with_dot_git(self):
        assert _parse_repo_arg("https://github.com/torvalds/linux.git") == "torvalds/linux"

    def test_ssh_url(self):
        assert _parse_repo_arg("git@github.com:torvalds/linux.git") == "torvalds/linux"

    def test_url_with_branch_suffix(self):
        assert _parse_repo_arg("https://github.com/torvalds/linux/tree/master") == "torvalds/linux"

    def test_empty_returns_empty_when_no_git(self, monkeypatch):
        """空参数 + 无 git 仓库时返回空字符串。"""
        monkeypatch.setattr("core.github_tools._run_gh",
                            lambda args, timeout=5: {"success": False, "stdout": "", "stderr": ""})
        assert _parse_repo_arg("") == ""

    def test_empty_auto_detects_current_repo(self, monkeypatch):
        """空参数自动检测当前仓库。"""
        monkeypatch.setattr("core.github_tools._run_gh",
                            lambda args, timeout=5: {"success": True, "stdout": "huangjiancheng/agnes-smart-studio"})
        assert _parse_repo_arg("") == "huangjiancheng/agnes-smart-studio"


# ── execute_github_search ──────────────────────────────────────────


class TestGithubSearch:
    """搜索工具参数拼接与错误处理。"""

    def test_search_repos_default(self, monkeypatch):
        fake = FakeGh(returns={"repos": {"success": True, "stdout": '{"items":[]}'}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_search(query="agnes"))
        assert "results" in result
        assert fake.calls[0][0] == "search" and fake.calls[0][1] == "repos"

    def test_search_issues_with_state_and_label(self, monkeypatch):
        fake = FakeGh(returns={"issues": {"success": True, "stdout": '[]'}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        execute_github_search(query="bug", search_type="issues", state="closed", label="bug")
        args = fake.calls[0]
        assert "--state" in args and "closed" in args
        assert "--label" in args and "bug" in args

    def test_search_invalid_type_returns_error(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh", FakeGh())
        result = json.loads(execute_github_search(query="x", search_type="invalid"))
        assert "error" in result

    def test_search_empty_query_returns_error(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh", FakeGh())
        result = json.loads(execute_github_search(query=""))
        assert "error" in result

    def test_search_gh_failure_returns_error(self, monkeypatch):
        fake = FakeGh(default={"success": False, "stderr": "API rate limit"})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_search(query="test"))
        assert "error" in result


# ── execute_github_repo_view ──────────────────────────────────────


class TestGithubRepoView:
    def test_repo_view_returns_data(self, monkeypatch):
        fake_data = {"name": "linux", "stargazerCount": 150000, "primaryLanguage": {"name": "C"}}
        fake = FakeGh(returns={"view": {"success": True, "stdout": json.dumps(fake_data)}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_repo_view(repo="torvalds/linux"))
        assert result["name"] == "linux"
        assert result["stargazerCount"] == 150000

    def test_repo_view_empty_repo_returns_error(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh",
                            lambda args, timeout=5: {"success": False, "stdout": ""})
        result = json.loads(execute_github_repo_view(repo=""))
        assert "error" in result


# ── execute_github_repo_list ───────────────────────────────────────


class TestGithubRepoList:
    def test_repo_list_returns_repos(self, monkeypatch):
        fake_data = [{"name": "repo1", "stargazerCount": 5}]
        fake = FakeGh(returns={"list": {"success": True, "stdout": json.dumps(fake_data)}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_repo_list())
        assert result["count"] == 1
        assert result["repos"][0]["name"] == "repo1"


# ── execute_github_browse ───────────────────────────────────────────


class TestGithubBrowse:
    def test_browse_directory(self, monkeypatch):
        fake_data = [
            {"name": "README.md", "type": "file", "path": "README.md", "size": 100},
            {"name": "src", "type": "dir", "path": "src", "size": 0},
        ]
        fake = FakeGh(default={"success": True, "stdout": json.dumps(fake_data)})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_browse(repo="torvalds/linux"))
        assert result["type"] == "directory"
        assert result["count"] == 2

    def test_browse_file_decodes_base64(self, monkeypatch):
        import base64
        content = "Hello, world!"
        fake_data = {
            "type": "file", "path": "hello.txt", "size": len(content),
            "sha": "abc123", "content": base64.b64encode(content.encode()).decode(),
        }
        fake = FakeGh(default={"success": True, "stdout": json.dumps(fake_data)})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_browse(repo="torvalds/linux", path="hello.txt"))
        assert result["type"] == "file"
        assert result["content"] == content


# ── execute_github_readme ──────────────────────────────────────────


class TestGithubReadme:
    def test_readme_returns_content(self, monkeypatch):
        import base64
        content = "# My Project\nHello!"
        fake_data = {"name": "README.md", "content": base64.b64encode(content.encode()).decode()}
        fake = FakeGh(default={"success": True, "stdout": json.dumps(fake_data)})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_readme(repo="torvalds/linux"))
        assert "# My Project" in result["content"]


# ── execute_github_release ────────────────────────────────────────


class TestGithubRelease:
    def test_release_list(self, monkeypatch):
        fake_data = [{"tagName": "v1.0", "name": "First release"}]
        fake = FakeGh(returns={"list": {"success": True, "stdout": json.dumps(fake_data)}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_release(repo="torvalds/linux"))
        assert result["releases"][0]["tagName"] == "v1.0"


# ── execute_github_issue ──────────────────────────────────────────


class TestGithubIssue:
    def test_issue_list(self, monkeypatch):
        fake_data = [{"number": 1, "title": "Bug", "state": "OPEN"}]
        fake = FakeGh(returns={"issue": {"success": True, "stdout": json.dumps(fake_data)}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_issue(repo="torvalds/linux", action="list"))
        assert result["action"] == "list"

    def test_issue_create_requires_title(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh", FakeGh())
        result = json.loads(execute_github_issue(repo="torvalds/linux", action="create"))
        assert "error" in result

    def test_issue_invalid_action(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh", FakeGh())
        result = json.loads(execute_github_issue(repo="torvalds/linux", action="delete"))
        assert "error" in result


# ── execute_github_pr ──────────────────────────────────────────────


class TestGithubPr:
    def test_pr_list(self, monkeypatch):
        fake_data = [{"number": 42, "title": "Fix bug", "state": "OPEN"}]
        fake = FakeGh(returns={"pr": {"success": True, "stdout": json.dumps(fake_data)}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_pr(repo="torvalds/linux"))
        assert result["results"][0]["number"] == 42


# ── execute_github_api ──────────────────────────────────────────────


class TestGithubApi:
    def test_api_basic_call(self, monkeypatch):
        fake = FakeGh(returns={"api": {"success": True, "stdout": '{"login":"test"}'}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_api(endpoint="user"))
        assert result["endpoint"] == "user"

    def test_api_empty_endpoint_returns_error(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh", FakeGh())
        result = json.loads(execute_github_api(endpoint=""))
        assert "error" in result

    def test_api_with_fields_parses_key_value(self, monkeypatch):
        fake = FakeGh(returns={"api": {"success": True, "stdout": "{}"}})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        execute_github_api(endpoint="repos/x/y", fields="title=MyTitle\nbody=MyBody")
        args = fake.calls[0]
        assert "-f" in args
        assert "title=MyTitle" in args
        assert "body=MyBody" in args


# ── execute_github_write_file ────────────────────────────────────────


class TestGithubWriteFile:
    def test_create_new_file(self, monkeypatch):
        """创建新文件：不含 sha。"""
        fake_resp = {
            "commit": {"sha": "abc123", "message": "Create hello.py", "html_url": "https://github.com/owner/repo/commit/abc123"},
            "content": {"sha": "def456", "path": "hello.py"},
        }
        fake = FakeGh(default={"success": True, "stdout": json.dumps(fake_resp)})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_write_file(repo="owner/repo", path="hello.py", content="print('hello')"))
        assert result["path"] == "hello.py"
        assert result["commit"]["sha"] == "abc123"
        assert result["commit"]["message"] == "Create hello.py"
        assert "url" in result
        # 验证传给 gh api 的参数
        args = fake.calls[0]
        assert "--method" in args and "PUT" in args
        assert "message=" in str(args)

    def test_update_existing_file_with_sha(self, monkeypatch):
        """更新已有文件：需要 sha。"""
        fake_resp = {
            "commit": {"sha": "new_commit", "message": "Update hello.py", "html_url": ""},
            "content": {"sha": "new_sha", "path": "hello.py"},
        }
        fake = FakeGh(default={"success": True, "stdout": json.dumps(fake_resp)})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        execute_github_write_file(repo="owner/repo", path="hello.py", content="v2", sha="old_sha", branch="fix-branch")
        args = fake.calls[0]
        assert "sha=old_sha" in args
        assert "branch=fix-branch" in args

    def test_empty_repo_returns_error(self, monkeypatch):
        monkeypatch.setattr("core.github_tools._run_gh",
                            lambda args, timeout=5: {"success": False, "stdout": ""})
        result = json.loads(execute_github_write_file(repo="", path="x.py", content="x"))
        assert "error" in result

    def test_empty_path_returns_error(self, monkeypatch):
        result = json.loads(execute_github_write_file(repo="owner/repo", path="", content="x"))
        assert "error" in result

    def test_empty_content_returns_error(self, monkeypatch):
        result = json.loads(execute_github_write_file(repo="owner/repo", path="x.py", content=""))
        assert "error" in result

    def test_gh_failure_returns_error(self, monkeypatch):
        fake = FakeGh(default={"success": False, "stderr": "409 File already exists"})
        monkeypatch.setattr("core.github_tools._run_gh", fake)
        result = json.loads(execute_github_write_file(repo="owner/repo", path="hello.py", content="x"))
        assert "error" in result

