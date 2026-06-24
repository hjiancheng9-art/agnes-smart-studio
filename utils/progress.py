"""Progress tracking — Rich progress bar + anti-rollback"""

from rich.progress import Progress

from ui.theme import LAYOUT

__all__ = ["VideoProgressTracker", "create_progress_callback"]


def create_progress_callback(progress_obj: Progress, task_id):
    """Create video progress callback with anti-rollback."""
    last_known_progress = [0]

    def _callback(status: str, progress: int, data: dict):
        # Anti-rollback: API may return simplified responses, keep last known progress
        if progress > 0:
            last_known_progress[0] = max(last_known_progress[0], progress)
        else:
            progress = last_known_progress[0]

        # Update progress bar with organic theme color
        progress_obj.update(task_id, completed=progress, description=f"[{LAYOUT['bar_style']}]{status}[/]")

    return _callback

    return _callback


class VideoProgressTracker:
    """视频生成进度追踪器（独立于Rich Progress使用）"""

    def __init__(self) -> None:
        self.last_known_progress: int | float = 0
        self.current_status = "queued"
        self.history: list[dict] = []

    def update(self, status: str, progress: int | float, data: dict):
        # 进度防回退
        raw = progress if isinstance(progress, (int, float)) else 0
        effective = max(self.last_known_progress, raw)
        self.last_known_progress = effective
        self.last_known_progress = effective
        self.current_status = status

        self.history.append(
            {
                "status": status,
                "progress": effective,
                "raw_progress": raw,
            }
        )

    @property
    def progress_percent(self) -> int | float:
        return min(100, self.last_known_progress)
