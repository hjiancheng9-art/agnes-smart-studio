"""Git workflow engine -- automated commit, branch, PR, and CI integration.

Provides structured git operations usable by the agent in autonomous mode.
All operations are safe (no force push, no destructive resets unless explicit).
"""

import time
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "GitWorkflow",
    "ROOT",
    "git_autocommit",
    "git_snapshot",
    "git_status",
]

ROOT = Path(__file__).resolve().parent.parent


class GitWorkflow:
    """Safe, structured git operations for autonomous agent use."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT

    def _run(self, *args, capture: bool = True) -> tuple[int, str, str]:
        r = run_subprocess(["git"] + list(args), timeout=30, cwd=str(self.root))
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def status(self) -> str:
        code, out, err = self._run("status", "--short")
        return out or "(clean)"

    def diff(self) -> str:
        code, out, err = self._run("diff", "--stat")
        return out or "(no changes)"

    def stage_all(self) -> str:
        code, out, err = self._run("add", "-A")
        return "all changes staged" if code == 0 else f"error: {err}"

    def commit(self, message: str) -> str:
        code, out, err = self._run("commit", "-m", message)
        return out or err

    def create_branch(self, name: str) -> str:
        safe_name = name.lower().replace(" ", "-")[:50]
        code, out, err = self._run("checkout", "-b", safe_name)
        return f"branch '{safe_name}' created" if code == 0 else err

    def current_branch(self) -> str:
        code, out, err = self._run("branch", "--show-current")
        return out or "unknown"

    def log(self, n: int = 5) -> str:
        code, out, err = self._run("log", f"-{n}", "--oneline", "--decorate")
        return out or "(no commits)"

    def safe_autocommit(self, message: str) -> dict:
        """Stage all changes, commit, return summary. Never pushes."""
        self.stage_all()
        dirty = self.status()
        if "(clean)" in dirty:
            return {"committed": False, "message": "nothing to commit"}
        commit_result = self.commit(message)
        return {
            "committed": True,
            "branch": self.current_branch(),
            "message": message,
            "git_output": commit_result,
        }

    def snapshot(self, label: str = "") -> str:
        """Quick git stash snapshot with label."""
        safe_label = label or f"auto-{int(time.time())}"
        code, out, err = self._run("stash", "push", "-m", safe_label)
        return f"snapshot '{safe_label}' saved" if code == 0 else err

    def restore_snapshot(self, label: str = "") -> str:
        """Pop most recent stash (or specific label)."""
        if label:
            code, out, err = self._run("stash", "list")
            for line in out.split("\n"):
                if label in line:
                    idx = line.split(":")[0].strip()
                    code, out, err = self._run("stash", "pop", idx)
                    return f"restored {idx}" if code == 0 else err
            return f"snapshot '{label}' not found"
        code, out, err = self._run("stash", "pop")
        return "restored latest snapshot" if code == 0 else err


def git_status() -> str:
    return GitWorkflow().status()


def git_autocommit(message: str) -> dict:
    return GitWorkflow().safe_autocommit(message)


def git_snapshot(label: str = "") -> str:
    return GitWorkflow().snapshot(label)
