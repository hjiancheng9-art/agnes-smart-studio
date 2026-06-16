#!/usr/bin/env python3
"""Agnes Smart Studio - 一键查询工具

自动从 history.json 提取最近未完成的视频任务并查询状态，
也可通过命令行参数指定 video_id。

用法:
    python query.py                          # 自动查询最近未完成任务
    python query.py VIDEO_ID                 # 查询指定视频
    python query.py VIDEO_ID --timeout 120   # 查询并限时等待完成
    python query.py --watch                  # 自动轮询，直到完成或失败
    python query.py --watch 15               # 每 15 秒轮询一次

⚠️ 必须使用 video_id 查询，不要使用 task_id，否则会导致排队异常延长。
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── 颜色 ──────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"
C = "\033[96m"; D = "\033[2m"; B = "\033[1m"; X = "\033[0m"


def _format_duration(seconds: float) -> str:
    """格式化秒数为可读时长"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    if seconds < 3600:
        return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
    return f"{int(seconds // 3600)}时{int((seconds % 3600) // 60)}分"


def _estimate_wait(created_at: int | None, status: str) -> str | None:
    """估算已等待时长"""
    if not created_at or status in ("completed", "failed"):
        return None
    elapsed = time.time() - created_at
    return _format_duration(elapsed)





def find_pending_tasks(history_path: Path) -> tuple[list[dict], list[dict]]:
    """从 history.json 中提取未完成的视频任务

    Returns:
        (queryable, unqueryable): 可查询的任务列表(有video_id) 和 无法查询的旧任务列表(仅task_id)
    """
    if not history_path.exists():
        return [], []

    history = json.loads(history_path.read_text(encoding="utf-8"))
    queryable = []
    unqueryable = []

    for item in reversed(history):
        result = item.get("result", {})

        # pipeline 模式
        if item.get("type") == "pipeline":
            video = result.get("video", {})
            task_id = video.get("task_id")
            video_id = video.get("video_id", "")
            status = video.get("status", "")
            if (task_id or video_id) and status in ("submitted", "processing", "queued", "pending", "in_progress"):
                entry = {
                    "task_id": task_id,
                    "video_id": video_id,
                    "status": status,
                    "prompt": item.get("prompt", ""),
                    "type": "pipeline",
                    "time": item.get("created_at", ""),
                }
                if video_id:
                    queryable.append(entry)
                else:
                    unqueryable.append(entry)

        # 独立视频模式
        elif item.get("type") in ("text_to_video", "image_to_video"):
            task_id = result.get("task_id")
            video_id = result.get("video_id", "")
            status = result.get("status", "")
            if (task_id or video_id) and status in ("submitted", "processing", "queued", "pending", "in_progress"):
                entry = {
                    "task_id": task_id,
                    "video_id": video_id,
                    "status": status,
                    "prompt": item.get("prompt", ""),
                    "type": item.get("type", ""),
                    "time": item.get("created_at", ""),
                }
                if video_id:
                    queryable.append(entry)
                else:
                    unqueryable.append(entry)

    return queryable, unqueryable


def query_task(video_id: str | None = None,
               timeout: float | None = None, watch: float | None = None):
    """查询指定任务状态

    Args:
        video_id: 视频ID（必须使用 video_id，不要用 task_id）
        timeout: 使用 wait_for_video 等待的最长秒数
        watch: 自动轮询间隔秒数（如 10 表示每 10s 查一次直到完成）
    """
    from core.client import AgnesClient

    with AgnesClient() as client:
        _query_task_impl(client, video_id=video_id, timeout=timeout, watch=watch)


def _query_task_impl(client, video_id: str | None = None,
                     timeout: float | None = None, watch: float | None = None):
    """内部实现：使用已有 client 查询任务状态，必须使用 video_id"""
    if not video_id:
        print(f"\n  {R}错误: 必须提供 video_id 查询视频状态{X}")
        print(f"  {D}请勿使用 task_id，否则会导致排队异常延长。{X}")
        print(f"  {D}video_id 可在创建视频任务的响应中获取。{X}\n")
        return

    data = client.check_video(video_id=video_id)

    status = data.get("status", "unknown")
    progress = data.get("progress", data.get("progress_ratio"))
    error = data.get("error")
    model = data.get("model", "")
    created_at = data.get("created_at")

    # 状态映射
    status_icon = {
        "completed": f"{G}✓{X}",
        "failed": f"{R}✗{X}",
        "processing": f"{Y}◉{X}",
        "in_progress": f"{Y}◉{X}",
        "queued": f"{Y}○{X}",
        "submitted": f"{Y}○{X}",
        "pending": f"{Y}○{X}",
    }.get(status, f"{D}?{X}")

    print(f"\n  {B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{X}")
    print(f"   任务查询结果")
    print(f"  {B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{X}")
    print(f"   视频ID:   {C}{video_id}{X}")
    print(f"   状态:     {status_icon} {status}")

    if model:
        print(f"   模型:     {D}{model}{X}")

    # 已等待时长
    waited = _estimate_wait(created_at, status)
    if waited:
        print(f"   已等待:   {Y}{waited}{X}")

    if progress is not None:
        try:
            pct = int(float(progress) * 100) if float(progress) <= 1 else int(float(progress))
            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"   进度:     {bar} {pct}%")
        except (ValueError, TypeError):
            print(f"   进度:     {progress}")

    # 如果已完成，显示结果
    if status == "completed":
        # API 返回的视频URL字段名为 remixed_from_video_id
        video_url = data.get("remixed_from_video_id") or data.get("video_url") or data.get("url", "")
        local_path = data.get("local_path", "")

        if video_url:
            print(f"   视频链接: {C}{video_url}{X}")
        if local_path:
            print(f"   本地文件: {G}{local_path}{X}")
        elif video_url:
            # 自动下载
            print(f"\n   {D}正在下载视频...{X}")
            try:
                from utils.downloader import download_video
                dl = download_video(video_url)
                if dl:
                    print(f"   {G}已下载到: {dl}{X}")
            except Exception:
                print(f"   {Y}下载失败，请手动访问链接{X}")

    elif status == "failed":
        error = data.get("error") or data.get("message", "未知错误")
        print(f"   错误:     {R}{error}{X}")

    print(f"  {B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{X}\n")

    # --watch 模式：自动轮询直到终态
    if watch and watch > 0 and status not in ("completed", "failed"):
        # 智能轮询：排队时拉长间隔，处理中缩短间隔
        base_interval = watch
        stable_count = 0  # 连续无变化的次数
        last_status = status
        last_progress = progress

        print(f"   {D}自动监控中，按 Ctrl+C 退出...{X}\n")
        try:
            while True:
                # 智能调整间隔
                if last_status == status and last_progress == progress:
                    stable_count += 1
                else:
                    stable_count = 0

                if status == "queued" and stable_count > 3:
                    # 排队中且无变化，间隔翻倍（最长60s）
                    interval = min(base_interval * (1 + stable_count * 0.3), 60)
                elif status in ("processing", "in_progress"):
                    # 处理中，缩短间隔以捕捉进度变化
                    interval = max(base_interval * 0.6, 5)
                else:
                    interval = base_interval

                last_status = status
                last_progress = progress

                time.sleep(interval)

                # 查询最新状态（429 时退避重试）
                now = datetime.now().strftime("%H:%M:%S")
                try:
                    data = client.check_video(video_id=video_id)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        backoff = min(interval * 2, 60)
                        print(f"   {Y}[{now}]{X} 请求过快，{backoff:.0f}s 后重试...")
                        time.sleep(backoff)
                        continue
                    raise
                status = data.get("status", "unknown")
                progress = data.get("progress", data.get("progress_ratio"))

                status_icon = {
                    "completed": f"{G}✓{X}", "failed": f"{R}✗{X}",
                    "processing": f"{Y}◉{X}", "in_progress": f"{Y}◉{X}",
                    "queued": f"{Y}○{X}",
                    "submitted": f"{Y}○{X}", "pending": f"{Y}○{X}",
                }.get(status, f"{D}?{X}")

                # 进度条
                progress_str = ""
                if progress is not None:
                    try:
                        pct = int(float(progress) * 100) if float(progress) <= 1 else int(float(progress))
                        bar_len = 20
                        filled = int(bar_len * pct / 100)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        progress_str = f"  {bar} {pct}%"
                    except (ValueError, TypeError):
                        progress_str = f"  进度: {progress}"

                # 排队等待时长
                waited_str = ""
                waited = _estimate_wait(data.get("created_at"), status)
                if waited:
                    waited_str = f"  {D}(已等{waited}){X}"

                print(f"   {D}[{now}]{X} {status_icon} {status}{progress_str}{waited_str}")

                if status in ("completed", "failed"):
                    print()
                    _query_task_impl(client, video_id=video_id, timeout=None, watch=None)
                    return
        except KeyboardInterrupt:
            print(f"\n\n   {D}已停止监控{X}")
            query_hint = video_id or ""
            print(f"   再次查询: python query.py {query_hint}{X}")
            print(f"   继续监控: python query.py {query_hint} --watch{X}\n")
        return

    # --timeout 模式：使用 wait_for_video 阻塞等待
    if timeout and timeout > 0 and status not in ("completed", "failed"):
        print(f"   {D}等待完成中（超时: {timeout}s）...{X}\n")
        try:
            client.wait_for_video(video_id=video_id, timeout=timeout)
            _query_task_impl(client, video_id=video_id, timeout=None, watch=None)
        except Exception as e:
            print(f"   {Y}等待超时或出错: {e}{X}")
            query_hint = video_id or ""
            print(f"   可再次运行: python query.py {query_hint}\n")


def main():
    history_path = Path(__file__).parent / "output" / "history.json"

    # 解析参数
    args = sys.argv[1:]
    video_id = None
    timeout = None
    watch = None

    i = 0
    while i < len(args):
        if args[i] == "--timeout" and i + 1 < len(args):
            timeout = float(args[i + 1])
            i += 2
        elif args[i] == "--watch":
            # --watch 15 或 --watch（默认 10s）
            if i + 1 < len(args) and args[i + 1].isdigit():
                watch = float(args[i + 1])
                i += 2
            else:
                watch = 10
                i += 1
        elif args[i].startswith("video_"):
            video_id = args[i]
            i += 1
        elif args[i].startswith("task_"):
            # ⚠️ task_id 不再支持查询，提示使用 video_id
            print(f"\n  {Y}警告: 不支持使用 task_id 查询，这会导致排队异常延长。{X}")
            print(f"  {D}请使用 video_id 查询（以 video_ 开头）。{X}\n")
            i += 1
        elif not args[i].startswith("--"):
            # 尝试作为 video_id 处理
            video_id = args[i]
            i += 1
        else:
            i += 1

    # 指定了 video_id，直接查询
    if video_id:
        query_task(video_id=video_id, timeout=timeout, watch=watch)
        return

    # 自动查找未完成任务
    pending, unqueryable = find_pending_tasks(history_path)

    # 提示无法查询的旧任务
    if unqueryable:
        print(f"\n  {Y}⚠ {len(unqueryable)} 个旧任务仅有 task_id 无 video_id，无法正确查询:{X}")
        for t in unqueryable:
            print(f"    {D}task_id: {t.get('task_id', 'N/A')}{X}")
            print(f"    {D}提示词: {t['prompt'][:40]}  ({t['time'][:19]}){X}")
        print(f"  {D}使用 task_id 查询会导致排队异常延长，建议忽略这些旧任务。{X}")

    if not pending:
        if not unqueryable:
            print(f"\n  {D}没有未完成的视频任务{X}")

            # 显示最近的任务供参考
            if history_path.exists():
                history = json.loads(history_path.read_text(encoding="utf-8"))
                if history:
                    print(f"\n  {D}最近的记录:{X}")
                    for item in history[:3]:
                        r = item.get("result", {})
                        t = item.get("type", "")
                        p = item.get("prompt", "")[:30]
                        created = item.get("created_at", "")[:19]
                        # 检查状态
                        if t == "pipeline":
                            s = r.get("video", {}).get("status", "completed")
                        else:
                            s = r.get("status", "completed")
                        print(f"    {D}{created}{X}  {C}{t}{X}  {p}...  [{s}]")
        print()
        return

    # 只有一个可查询任务，直接查询
    if len(pending) == 1:
        t = pending[0]
        vid = t.get("video_id", "")
        print(f"\n  {C}发现 1 个未完成任务:{X}")
        print(f"    {vid}")
        print(f"    提示词: {t['prompt'][:40]}")
        print(f"    时间:   {t['time'][:19]}")
        query_task(video_id=vid, timeout=timeout, watch=watch)
        return

    # 多个可查询任务，列出选择
    print(f"\n  {C}发现 {len(pending)} 个可查询的未完成任务:{X}\n")
    for i, t in enumerate(pending, 1):
        vid = t.get("video_id", "")
        print(f"    {B}{i}{X}. {vid}")
        print(f"       提示词: {t['prompt'][:40]}")
        print(f"       时间:   {t['time'][:19]}")
        print()

    try:
        choice = input(f"  选择要查询的任务 (1-{len(pending)}, 回车查询全部): ").strip()
        if choice == "":
            for t in pending:
                vid = t.get("video_id", "")
                if vid:
                    query_task(video_id=vid, timeout=timeout, watch=watch)
        else:
            idx = int(choice) - 1
            if 0 <= idx < len(pending):
                t = pending[idx]
                vid = t.get("video_id", "")
                if vid:
                    query_task(video_id=vid, timeout=timeout, watch=watch)
            else:
                print(f"  {R}无效选择{X}")
    except (ValueError, KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
