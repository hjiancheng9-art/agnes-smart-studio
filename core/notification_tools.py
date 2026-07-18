"""System notification tools — desktop toast notifications.

Tools:
    notify_send  Send a desktop notification
"""

from __future__ import annotations

import json
import platform
import subprocess


def notify_send(title: str, message: str, duration: int = 5) -> str:
    """Send a desktop toast notification.

    Args:
        title: Notification title
        message: Notification body text
        duration: Display duration in seconds (default 5)

    Returns:
        JSON with status
    """
    if not title or not message:
        return "[错误] title 和 message 参数不能为空"

    system = platform.system()

    if system == "Windows":
        return _win_notify(title, message, duration)
    elif system == "Darwin":
        return _mac_notify(title, message)
    else:
        return _linux_notify(title, message, duration)


def _win_notify(title: str, message: str, duration: int) -> str:
    """Windows notification via PowerShell."""
    # Escape double quotes for PowerShell
    escaped_title = title.replace('"', '`"').replace("'", "''")
    escaped_msg = message.replace('"', '`"').replace("'", "''")

    ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("{escaped_title}")) > $null
$textNodes.Item(1).AppendChild($template.CreateTextNode("{escaped_msg}")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("CRUX Studio")
$notifier.Show($toast)
'''

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=0x08000000,
        )
        if proc.returncode == 0:
            return json.dumps({"status": "ok", "platform": "Windows", "method": "toast"}, ensure_ascii=False)
        # Fallback: MessageBox
        return _win_msgbox(title, message)
    except Exception:
        return _win_msgbox(title, message)


def _win_msgbox(title: str, message: str) -> str:
    """Windows fallback: MessageBox via ctypes."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
        return json.dumps({"status": "ok", "platform": "Windows", "method": "messagebox"}, ensure_ascii=False)
    except Exception as e:
        return f"[错误] Windows 通知失败: {e}"


def _mac_notify(title: str, message: str) -> str:
    """macOS notification via osascript."""
    escaped_title = title.replace('"', '\\"')
    escaped_msg = message.replace('"', '\\"')
    script = f'display notification "{escaped_msg}" with title "{escaped_title}"'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return json.dumps({"status": "ok", "platform": "Darwin", "method": "osascript"}, ensure_ascii=False)
        return f"[错误] macOS 通知失败: {proc.stderr.strip()}"
    except Exception as e:
        return f"[错误] macOS 通知失败: {e}"


def _linux_notify(title: str, message: str, duration: int) -> str:
    """Linux notification via notify-send."""
    try:
        proc = subprocess.run(
            ["notify-send", title, message, "-t", str(duration * 1000)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return json.dumps({"status": "ok", "platform": "Linux", "method": "notify-send"}, ensure_ascii=False)
        return f"[错误] Linux 通知失败: {proc.stderr.strip()}"
    except FileNotFoundError:
        return "[错误] 未找到 notify-send 命令。请安装: sudo apt install libnotify-bin"
    except Exception as e:
        return f"[错误] Linux 通知失败: {e}"
