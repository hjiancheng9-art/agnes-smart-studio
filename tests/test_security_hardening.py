"""批次 D 安全守卫回归测试 (P0-6/7/8, P1-15)。

验证：
- P0-6: sandbox 路径白名单覆盖 Windows 绝对路径 (C:\\ / \\\\host\\)
- P0-7: DANGEROUS_PATTERNS 覆盖 Windows 破坏性命令 (rmdir /s, del /f, format)
- P1-15: git_tools.execute_git_push(force=True) 在执行器层二次拦截
- P0-8: ChatSession._dispatch_tool 扩展的高风险工具确认
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ════════════════════════════════════════════════════════════
#  P0-6: Windows 绝对路径检测
# ════════════════════════════════════════════════════════════

class TestWindowsPathDetection:
    """sandbox.validate 应识别 Windows 绝对路径越界。"""

    def test_windows_drive_path_outside_root_blocked(self):
        from core.sandbox import sandbox_check
        # C:\\Windows\\System32 不在 ALLOWED_ROOTS 中（除非 ROOT 恰好是 C:\\）
        # 使用一个明确不在白名单的虚构盘符避免与测试环境耦合
        ok, _ = sandbox_check("type Z:\\evil\\secret.txt")
        assert ok is False

    def test_windows_unc_path_blocked(self):
        from core.sandbox import sandbox_check
        ok, _ = sandbox_check("copy \\\\attacker\\share\\payload.exe .")
        assert ok is False

    def test_unix_path_still_detected(self):
        """回归：原 Unix 路径检测不因新增 Windows 检测而失效。

        注意：pathlib.Path("/etc/x").is_absolute() 在 Windows 上返回 False，
        故 Unix 风格路径检测只在非 Windows 平台生效（跨平台行为，非 bug）。
        """
        import sys as _sys
        if _sys.platform == "win32":
            pytest.skip("Unix 路径检测在 Windows pathlib 下天然不生效")
        from core.sandbox import sandbox_check
        ok, _ = sandbox_check("cat /etc/shadow")
        assert ok is False


# ════════════════════════════════════════════════════════════
#  P0-7: Windows 破坏性命令模式
# ════════════════════════════════════════════════════════════

class TestWindowsDangerousPatterns:
    """DANGEROUS_PATTERNS 应拦截 Windows 破坏性命令。"""

    @pytest.mark.parametrize("cmd", [
        "rmdir /s /q C:\\temp",
        "del /f /s /q important.bin",
        "erase /f sensitive.dat",
        "format D:",
        "diskpart /script diskwipe.txt",
        "cipher /w:C:\\",
        "reg delete HKLM\\Software\\X /f",
    ])
    def test_windows_destructive_command_blocked(self, cmd):
        from core.sandbox import sandbox_check
        ok, _ = sandbox_check(cmd)
        assert ok is False, f"应拦截破坏性命令: {cmd}"

    def test_unix_destructive_still_blocked(self):
        """回归：原 Unix 危险模式仍生效。"""
        from core.sandbox import sandbox_check
        for cmd in ["rm -rf /tmp/x", "git push --force", "git reset --hard HEAD~1"]:
            ok, _ = sandbox_check(cmd)
            assert ok is False, f"应拦截: {cmd}"

    def test_legitimate_windows_command_passes(self):
        """合法 Windows 命令不应被误杀。"""
        from core.sandbox import sandbox_check
        # 无绝对路径 + 非破坏性
        ok, _ = sandbox_check("echo hello")
        assert ok is True


# ════════════════════════════════════════════════════════════
#  P1-15: git_tools.execute_git_push force 拦截
# ════════════════════════════════════════════════════════════

class TestGitPushForceBlocked:
    """execute_git_push(force=True) 必须返回错误而非执行。"""

    def test_force_push_returns_confirm_required(self):
        import json
        from core.git_tools import execute_git_push
        result = execute_git_push(remote="origin", branch="main", force=True)
        data = json.loads(result)
        assert data.get("needs_confirm") is True
        assert "error" in data
        # 关键：不应有 pushed 字段（说明没真执行）
        assert "pushed" not in data

    def test_normal_push_executes(self, monkeypatch):
        """非 force 推送应正常走 _run_git（mock 验证不被拦截）。"""
        import json
        import core.git_tools as gt
        # mock _run_git 避免真跑 git
        called_args = []

        def fake_run_git(args, cwd=""):
            called_args.append(args)
            return {"success": True, "stdout": "ok", "stderr": "", "exit_code": 0}

        monkeypatch.setattr(gt, "_run_git", fake_run_git)
        result = execute_git_push_proxy = gt.execute_git_push(
            remote="origin", branch="feature-x", force=False
        )
        data = json.loads(result)
        assert data.get("pushed") is True
        # 确认没插入 --force
        assert "--force" not in called_args[0]


# ════════════════════════════════════════════════════════════
#  P0-8: ChatSession 高风险工具确认扩展
# ════════════════════════════════════════════════════════════

class TestHighRiskToolConfirmation:
    """_dispatch_tool 应对扩展的高风险场景返回 confirm 副作用。"""

    def _make_session(self):
        from unittest.mock import MagicMock
        from core.chat import ChatSession
        mock_client = MagicMock()
        return ChatSession(mock_client)

    def test_force_push_triggers_confirm(self):
        from core.chat import ChatSession
        s = self._make_session()
        _, side = ChatSession._dispatch_tool(
            s, "git_push",
            '{"remote": "origin", "branch": "main", "force": true}',
        )
        assert any(k == "confirm" for k, _ in side), \
            "git_push + force=true 应触发 confirm 副作用"

    def test_git_branch_delete_triggers_confirm(self):
        from core.chat import ChatSession
        s = self._make_session()
        _, side = ChatSession._dispatch_tool(
            s, "git_branch",
            '{"name": "feature-old", "action": "delete"}',
        )
        assert any(k == "confirm" for k, _ in side)

    def test_git_worktree_force_remove_triggers_confirm(self):
        from core.chat import ChatSession
        s = self._make_session()
        _, side = ChatSession._dispatch_tool(
            s, "git_worktree",
            '{"action": "remove", "path": "/tmp/wt", "force": true}',
        )
        assert any(k == "confirm" for k, _ in side)

    def test_normal_git_branch_list_no_confirm(self):
        """只读操作不应触发确认。"""
        from core.chat import ChatSession
        s = self._make_session()
        # list action 会进入 ToolRegistry.execute 路径（返回结果，无 confirm）
        _, side = ChatSession._dispatch_tool(
            s, "git_branch", '{"action": "list"}'
        )
        assert not any(k == "confirm" for k, _ in side)

    def test_risky_bash_pattern_triggers_confirm(self):
        """run_bash 含 rm/delete/drop/format 仍触发确认。"""
        from core.chat import ChatSession
        s = self._make_session()
        _, side = ChatSession._dispatch_tool(
            s, "run_bash", '{"command": "find . -name x -delete"}'
        )
        assert any(k == "confirm" for k, _ in side)
