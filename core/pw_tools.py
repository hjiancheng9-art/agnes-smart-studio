"""
pw_tools.py — 独立的 Playwright 工具函数。
每个函数通过 subprocess 调用 pw_worker.py，完全避开 sync_playwright + asyncio 冲突。
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pw_run(action: str, **kwargs) -> dict:
    """Run a Playwright action in a clean subprocess via pw_worker.py."""
    args = [sys.executable, str(ROOT / "core" / "pw_worker.py"), action]
    for k, v in kwargs.items():
        args.append(f"{k}={v}")

    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=45,
            encoding="utf-8",
            cwd=str(ROOT),
        )
        for line in r.stdout.strip().split("\n"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"error": f"pw_worker rc={r.returncode}: {r.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"error": "pw_worker timeout (45s)"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def navigate(url: str) -> str:
    """Navigate Playwright browser to URL."""
    r = _pw_run("navigate", url=url)
    if r.get("error"):
        return f"[错误] {r['error']}"
    return f"已导航: {r.get('url', url)} — {r.get('title', '')}"


def screenshot(url: str = "") -> str:
    """Take a full-page screenshot."""
    path = str(ROOT / "output" / f"browser_{int(time.time())}.png")
    kwargs = {"path": path}
    if url:
        kwargs["url"] = url
    r = _pw_run("screenshot", **kwargs)
    if r.get("error"):
        return f"[错误] {r['error']}"
    return r.get("path", path)
