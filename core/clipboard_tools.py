"""Clipboard tools — system clipboard read/write.

Tools:
    clipboard_copy  Copy text to system clipboard
    clipboard_paste Get text from system clipboard
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess


def _win_copy(text: str) -> bool:
    """Copy text via Windows clip.exe."""
    try:
        proc = subprocess.run(
            ["clip"],
            input=text,
            text=True,
            timeout=5,
            creationflags=0x08000000 if platform.system() == "Windows" else 0,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _win_paste() -> str | None:
    """Paste text via PowerShell Get-Clipboard."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000,
        )
        if proc.returncode == 0:
            return proc.stdout.rstrip("\n\r")
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)
    return None


def _mac_copy(text: str) -> bool:
    try:
        return subprocess.run(["pbcopy"], input=text, text=True, timeout=5).returncode == 0
    except Exception:
        return False


def _mac_paste() -> str | None:
    try:
        proc = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        return proc.stdout.rstrip("\n\r") if proc.returncode == 0 else None
    except Exception:
        return None


def _linux_copy(text: str) -> bool:
    for cmd in ["xclip -selection clipboard", "xsel --clipboard --input"]:
        binary = cmd.split()[0]
        if shutil.which(binary):
            try:
                return subprocess.run(cmd.split(), input=text, text=True, timeout=5).returncode == 0
            except Exception:
                import logging

                logging.getLogger(__name__).debug("silent except", exc_info=True)
    return False


def _linux_paste() -> str | None:
    for cmd in ["xclip -selection clipboard -o", "xsel --clipboard --output"]:
        binary = cmd.split()[0]
        if shutil.which(binary):
            try:
                proc = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    return proc.stdout.rstrip("\n\r")
            except Exception:
                import logging

                logging.getLogger(__name__).debug("silent except", exc_info=True)
    return None


def clipboard_copy(text: str) -> str:
    """Copy text to system clipboard.

    Args:
        text: Text content to copy to clipboard

    Returns:
        JSON with status and platform info
    """
    if not text:
        return "[错误] text 参数不能为空"

    system = platform.system()
    ok = False

    if system == "Windows":
        ok = _win_copy(text)
    elif system == "Darwin":
        ok = _mac_copy(text)
    else:
        ok = _linux_copy(text)

    if ok:
        return json.dumps({"status": "ok", "platform": system, "length": len(text)}, ensure_ascii=False)
    return json.dumps(
        {"status": "error", "platform": system, "message": "剪贴板操作失败，请确认系统安装了 clip/xclip/xsel"},
        ensure_ascii=False,
    )


def clipboard_paste() -> str:
    """Get text from system clipboard.

    Returns:
        JSON with clipboard text content
    """
    system = platform.system()
    text: str | None = None

    if system == "Windows":
        text = _win_paste()
    elif system == "Darwin":
        text = _mac_paste()
    else:
        text = _linux_paste()

    if text is not None:
        return json.dumps({"status": "ok", "text": text, "platform": system, "length": len(text)}, ensure_ascii=False)
    return json.dumps(
        {"status": "error", "platform": system, "message": "无法读取剪贴板，请确认系统安装了 clip/xclip/xsel"},
        ensure_ascii=False,
    )
