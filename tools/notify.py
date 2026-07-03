"""Desktop notification — Windows toast for long-running task completion.

Mirrors Claude Code's notify.ps1 hook. Uses Windows.UI.Notifications via
PowerShell (no external dependency).
"""

import subprocess
import sys


def notify(title: str = "CRUX Studio", message: str = "") -> None:
    """Send a Windows desktop notification."""
    if sys.platform != "win32":
        print(f"[CRUX] {title}: {message}")
        return

    ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName("text")
$texts[0].AppendChild($template.CreateTextNode("{title}")) > $null
$texts[1].AppendChild($template.CreateTextNode("{message}")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("CRUX Studio").Show($toast)
'''
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, timeout=5,
        )
    except Exception:
        print(f"[CRUX] {title}: {message}")


# ── CLI ───────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Send desktop notification")
    p.add_argument("message", nargs="*", help="Notification message")
    p.add_argument("--title", default="CRUX Studio", help="Notification title")
    args = p.parse_args()
    notify(args.title, " ".join(args.message))
