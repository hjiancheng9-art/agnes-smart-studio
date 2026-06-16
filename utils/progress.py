"""进度追踪 - Rich进度条 + 进度防回退"""

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn


def create_progress_callback(progress_obj: Progress, task_id):
    """创建视频进度回调函数，内置进度防回退"""
    last_known_progress = [0]

    def _callback(status: str, progress: int, data: dict):
        # 进度防回退：API 偶发返回简化响应，保持上次已知进度
        if progress > 0:
            last_known_progress[0] = max(last_known_progress[0], progress)
        else:
            progress = last_known_progress[0]

        # 更新进度条
        progress_obj.update(task_id, completed=progress, description=f"[cyan]{status}[/]")

    return _callback


class VideoProgressTracker:
    """视频生成进度追踪器（独立于Rich Progress使用）"""

    def __init__(self):
        self.last_known_progress = 0
        self.current_status = "queued"
        self.history: list[dict] = []

    def update(self, status: str, progress: int | float, data: dict):
        # 进度防回退
        raw = progress if isinstance(progress, (int, float)) else 0
        effective = max(self.last_known_progress, raw)
        self.last_known_progress = effective
        self.current_status = status

        self.history.append({
            "status": status,
            "progress": effective,
            "raw_progress": raw,
        })

    @property
    def progress_percent(self) -> int:
        return min(100, self.last_known_progress)
