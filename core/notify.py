"""Desktop notification system for async task completion."""

import subprocess
import platform


__all__ = ["Notifier", "notify", "notify_task_done"]
class Notifier:
    def __init__(self) -> None:
        self._os = platform.system()
        self._available = self._check_available()

    def _check_available(self) -> bool:
        if self._os == "Windows":
            try:
                r = subprocess.run(["where", "powershell"], capture_output=True, timeout=3)
                return r.returncode == 0
            except (subprocess.SubprocessError, OSError):
                return False
        elif self._os == "Darwin":
            try:
                r = subprocess.run(["which", "osascript"], capture_output=True, timeout=3)
                return r.returncode == 0
            except (subprocess.SubprocessError, OSError):
                return False
        else:
            try:
                r = subprocess.run(["which", "notify-send"], capture_output=True, timeout=3)
                return r.returncode == 0
            except (subprocess.SubprocessError, OSError):
                return False

    def send(self, title: str, message: str, urgent: bool = False):
        if not self._available:
            return
        # 转义注入字符，防止命令注入
        _safe_title = title.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        _safe_msg = message.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        try:
            if self._os == "Windows":
                ps_script = (
                    '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; '
                    f'$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02; '
                    f'$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template); '
                    f'$xml.GetElementsByTagName("text")[0].AppendChild($xml.CreateTextNode("{_safe_title}")) > $null; '
                    f'$xml.GetElementsByTagName("text")[1].AppendChild($xml.CreateTextNode("{_safe_msg}")) > $null; '
                    f'$toast = New-Object Windows.UI.Notifications.ToastNotification($xml); '
                    f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Agnes").Show($toast)'
                )
                subprocess.Popen(
                    ["powershell", "-Command", ps_script],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif self._os == "Darwin":
                subprocess.Popen(
                    ["osascript", "-e",
                     f'display notification "{_safe_msg}" with title "{_safe_title}"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                urgency = "--urgency=critical" if urgent else ""
                subprocess.Popen(
                    ["notify-send", urgency, title, message],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        except (subprocess.SubprocessError, OSError):
            import logging
            logging.getLogger("agnes.notify").warning("Notification failed", exc_info=True)


_notifier = Notifier()


def notify(title: str, message: str, urgent: bool = False):
    _notifier.send(title, message, urgent)


def notify_task_done(task_type: str, result: str = ""):
    messages = {
        "video": ("Video Ready", "Your video generation is complete."),
        "image": ("Image Ready", "Image generation complete."),
        "self_evolve": ("Evolution Complete", result or "Self-evolution finished."),
        "audit": ("Audit Complete", f"Self-audit found {result}."),
        "fix": ("Auto-fix Complete", result or "Auto-fix applied."),
    }
    title, msg = messages.get(task_type, ("Task Complete", f"{task_type} finished."))
    notify(title, msg)