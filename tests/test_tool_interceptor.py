"""Tests for core/tool_interceptor.py — PreToolUse safety interceptor."""

from core.tool_interceptor import intercept_tool


class TestInterceptBashBlocked:
    """Commands that should be BLOCKED (return False, reason)."""

    def test_rm_rf_root_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "rm -rf /"})
        assert allowed is False
        assert "BLOCKED" in reason

    def test_rm_rf_home_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "rm -rf ~/projects"})
        assert allowed is False

    def test_dd_to_block_device_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "dd if=/dev/zero of=/dev/sdb"})
        assert allowed is False

    def test_mkfs_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "mkfs.ext4 /dev/sda1"})
        assert allowed is False

    def test_chmod_777_root_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "chmod 777 /"})
        assert allowed is False

    def test_git_force_push_main_blocked(self):
        allowed, reason = intercept_tool("run_bash", {"command": "git push --force origin main"})
        assert allowed is False

    def test_case_insensitive_blocking(self):
        allowed, reason = intercept_tool("run_bash", {"command": "RM -RF /"})
        assert allowed is False


class TestInterceptBashWarned:
    """Commands that should trigger WARNING but not blocked."""

    def test_pip_uninstall_warned(self):
        allowed, reason = intercept_tool("run_bash", {"command": "pip uninstall requests"})
        assert allowed is True
        assert "WARNING" in reason

    def test_npm_uninstall_warned(self):
        allowed, reason = intercept_tool("run_bash", {"command": "npm uninstall react"})
        assert allowed is True
        assert "WARNING" in reason

    def test_git_reset_hard_warned(self):
        allowed, reason = intercept_tool("run_bash", {"command": "git reset --hard HEAD~1"})
        assert allowed is True
        assert "WARNING" in reason

    def test_git_clean_f_warned(self):
        allowed, reason = intercept_tool("run_bash", {"command": "git clean -fd"})
        assert allowed is True
        assert "WARNING" in reason


class TestInterceptBashSafe:
    """Safe commands pass through."""

    def test_empty_command_passes(self):
        allowed, reason = intercept_tool("run_bash", {})
        assert allowed is True
        assert reason == ""

    def test_safe_command_passes(self):
        allowed, reason = intercept_tool("run_bash", {"command": "ls -la"})
        assert allowed is True
        assert reason == ""

    def test_git_status_passes(self):
        allowed, reason = intercept_tool("run_bash", {"command": "git status"})
        assert allowed is True

    def test_python_command_passes(self):
        allowed, reason = intercept_tool("run_bash", {"command": "python -m pytest"})
        assert allowed is True


class TestInterceptFileWrite:
    """Protected file interception."""

    def test_write_env_blocked(self):
        allowed, reason = intercept_tool("write_file", {"file_path": "/some/path/.env"})
        assert allowed is False
        assert "BLOCKED" in reason

    def test_write_credentials_blocked(self):
        allowed, reason = intercept_tool("edit_file", {"file_path": "credentials.json"})
        assert allowed is False

    def test_write_id_rsa_blocked(self):
        allowed, reason = intercept_tool("write_file", {"file_path": "~/.ssh/id_rsa"})
        assert allowed is False

    def test_write_pem_blocked(self):
        allowed, reason = intercept_tool("patch_file", {"file_path": "cert.pem"})
        assert allowed is False

    def test_write_service_account_blocked(self):
        allowed, reason = intercept_tool("edit_file", {"file_path": "service-account.json"})
        assert allowed is False

    def test_write_normal_file_passes(self):
        allowed, reason = intercept_tool("write_file", {"file_path": "src/main.py"})
        assert allowed is True

    def test_write_readme_passes(self):
        allowed, reason = intercept_tool("write_file", {"file_path": "README.md"})
        assert allowed is True

    def test_empty_path_passes(self):
        allowed, reason = intercept_tool("write_file", {})
        assert allowed is True

    def test_unknown_tool_passes(self):
        allowed, reason = intercept_tool("some_unknown_tool", {"x": 1})
        assert allowed is True
        assert reason == ""


class TestInterceptCmdAlias:
    """bash commands using 'cmd' key."""

    def test_rm_with_cmd_key(self):
        allowed, reason = intercept_tool("run_bash", {"cmd": "rm -rf /"})
        assert allowed is False

    def test_safe_with_cmd_key(self):
        allowed, reason = intercept_tool("run_bash", {"cmd": "echo safe"})
        assert allowed is True


class TestGateCdpChatgpt:
    """CDP ChatGPT gatekeeping — pure logic paths."""

    def test_too_short_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "hi"})
        assert blocked is True
        assert "太短" in reason

    def test_empty_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": ""})
        assert blocked is True

    def test_repetitive_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "aaaaa"})
        assert blocked is True

    def test_trivial_hello_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "你好"})
        assert blocked is True

    def test_trivial_what_is_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "什么是Python"})
        assert blocked is True

    def test_code_operation_blocked(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "帮我改一下这个bug"})
        assert blocked is True
        assert "DeepSeek" in reason

    def test_legitimate_question_passes(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"question": "请分析中美贸易战的最新进展和各方立场"})
        assert blocked is False
        assert reason == ""

    def test_alternate_key_text(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt(
            {"text": "How does quantum computing affect blockchain security in the long term?"}
        )
        assert blocked is False

    def test_alternate_key_prompt(self):
        from core.tool_interceptor import _gate_cdp_chatgpt

        blocked, reason = _gate_cdp_chatgpt({"prompt": "hi"})
        assert blocked is True
