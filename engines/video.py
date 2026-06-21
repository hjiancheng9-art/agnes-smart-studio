"""视频生成引擎 - 4种模式 + 异步轮询 + 进度防回退 + 双通道查询"""
import threading
from datetime import datetime

import httpx

from core.client import AgnesClient
from core.config import OUTPUT_DIR, SETTINGS
from core.validator import validate_num_frames, validate_frame_rate, validate_seed, validate_image_urls, validate_video_resolution
import contextlib

__all__ = ['VideoEngine', 'VideoFuture']



class VideoFuture:
    """Handle to a background video generation task.

    The video is submitted and polled in a daemon thread so the main session
    stays responsive. Caller can check progress, wait for completion, or cancel.
    """

    def __init__(self, video_id: str, task_id: str, prompt: str, num_frames: int):
        self.video_id = video_id
        self.task_id = task_id
        self.prompt = prompt
        self.num_frames = num_frames
        self._done = threading.Event()
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._progress: float = 0.0
        self._result: dict | None = None
        self._error: Exception | None = None
        self._status: str = "submitted"

    @property
    def progress(self) -> float:
        with self._lock:
            return self._progress

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    def is_done(self) -> bool:
        return self._done.is_set()

    def cancel(self):
        """Signal the background poller to stop polling."""
        self._cancel.set()
        self._done.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for completion. Returns True if done, False if timeout."""
        return self._done.wait(timeout=timeout)

    def get_result(self) -> dict:
        """Get final result. Blocks until done. Raises if polling failed."""
        self._done.wait()
        if self._error:
            raise self._error
        if self._result is None:
            raise RuntimeError(f"Video {self.video_id}: no result available")
        return self._result


def _clean_video_id(raw: str) -> str:
    """清洗 litellm 包装的 video_id，提取真实 ID。

    API 可能返回: video_<base64(litellm:...;video_id:video_xxx)>
    清洗后: video_xxx
    """
    import logging
    _log = logging.getLogger(__name__)

    if not raw or not raw.startswith("video_"):
        return raw
    # 尝试 base64 解码 video_ 之后的部分
    import base64
    try:
        b64_part = raw[6:]  # 去掉 "video_" 前缀
        decoded = base64.b64decode(b64_part).decode("utf-8")
        if "video_id:" in decoded:
            idx = decoded.rfind("video_id:")
            return decoded[idx + len("video_id:"):]
    except (ValueError, UnicodeDecodeError):
        pass
    # 如果不在 base64 里，检查明文
    if "litellm:" in raw and ";video_id:" in raw:
        idx = raw.rfind("video_id:")
        if idx >= 0:
            return raw[idx + len("video_id:"):]
    _log.warning("_clean_video_id: unable to decode video_id=%s, returning raw", raw[:80])
    return raw


class VideoEngine:
    def __init__(self, client: AgnesClient):
        self.client = client

    def submit_only(self, prompt, width=1152, height=768, num_frames=121,
                    frame_rate=24, image=None, negative_prompt=None,
                    seed=None, num_inference_steps=40, extra_body=None) -> dict:
        """仅提交视频任务，不轮询等待。返回 video_id 和 task_id，适合分步操作避免阻塞。"""
        width, height = validate_video_resolution(width, height)
        num_frames = validate_num_frames(num_frames)
        frame_rate = validate_frame_rate(frame_rate)
        seed = validate_seed(seed)

        task = self.client.create_video(
            prompt=prompt, width=width, height=height, num_frames=num_frames,
            frame_rate=frame_rate, image=image,
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps, extra_body=extra_body,
        )
        task_id = task.get("task_id") or task.get("id")
        video_id = _clean_video_id(task.get("video_id", ""))
        return {"task_id": task_id, "video_id": video_id, "status": "submitted",
                "model": "agnes-video-v2.0", "prompt": prompt, "num_frames": num_frames}

    def submit_async(self, prompt, width=1152, height=768, num_frames=121,
                     frame_rate=24, image=None, negative_prompt=None,
                     seed=None, num_inference_steps=40, extra_body=None,
                     timeout=None) -> VideoFuture:
        """Submit a video task and return a VideoFuture for background polling.

        The video is submitted synchronously (fast), then polling runs in a
        daemon thread. The caller can check progress, wait, or cancel via
        the returned VideoFuture.

        Returns:
            VideoFuture with .progress, .is_done(), .wait(), .get_result(), .cancel()
        """
        import sys
        import traceback

        submitted = self.submit_only(
            prompt=prompt, width=width, height=height,
            num_frames=num_frames, frame_rate=frame_rate,
            image=image, negative_prompt=negative_prompt,
            seed=seed, num_inference_steps=num_inference_steps,
            extra_body=extra_body,
        )
        video_id = submitted["video_id"]
        task_id = submitted["task_id"]
        future = VideoFuture(
            video_id=video_id, task_id=task_id,
            prompt=prompt, num_frames=num_frames,
        )

        def _poll_worker():
            try:
                def on_progress(status, progress, data):
                    with future._lock:
                        future._progress = progress
                        future._status = status

                if timeout is not None:
                    result = self.client.wait_for_video(
                        video_id=video_id,
                        timeout=timeout,
                        interval=SETTINGS.video_poll_interval,
                        on_progress=on_progress,
                    )
                else:
                    result = self.client.poll_video(
                        video_id=video_id,
                        interval=SETTINGS.video_poll_interval,
                        max_wait=SETTINGS.video_max_wait,
                        on_progress=on_progress,
                    )

                # 检查取消信号（在锁外读取 is_set 安全——一旦 set 永不 unset）
                if future._cancel.is_set():
                    return

                if result is None:
                    # poll_video 超时应由 TimeoutError 处理，防御性兜底
                    with future._lock:
                        future._status = "timeout"
                    return

                timed_out = result.pop("_timed_out", False)
                video_url = result.get("remixed_from_video_id") or result.get("video_url", "")
                local_path = ""
                if video_url and video_url.startswith("http") and not timed_out:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    local_path = str(OUTPUT_DIR / "videos" / f"vid_{ts}.mp4")
                    with contextlib.suppress(RuntimeError):
                        self.client.download_video(video_url, local_path)

                ret = {
                    "url": video_url, "local_path": local_path,
                    "task_id": task_id, "video_id": video_id,
                    "model": "agnes-video-v2.0", "prompt": prompt,
                    "num_frames": num_frames,
                }
                if timed_out:
                    ret["status"] = "timeout"
                    ret["progress"] = result.get("progress", 0)

                with future._lock:
                    future._result = ret
                    future._status = "timeout" if timed_out else "complete"
            except (httpx.HTTPError, OSError, KeyError) as e:
                print(f"[warn] Background video poll failed for {video_id}: {e}",
                      file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                with future._lock:
                    future._error = e
                    future._status = "failed"
            finally:
                future._done.set()

        t = threading.Thread(target=_poll_worker, daemon=True,
                             name=f"video-poll-{video_id[:20]}")
        t.start()
        return future

    def submit_and_wait(self, prompt, width=1152, height=768, num_frames=121,
                        frame_rate=24, image=None, negative_prompt=None,
                        seed=None, num_inference_steps=40, extra_body=None,
                        on_progress=None, timeout=None) -> dict:
        """提交视频任务并限时等待（自动绕过内容过滤）"""
        width, height = validate_video_resolution(width, height)
        num_frames = validate_num_frames(num_frames)
        frame_rate = validate_frame_rate(frame_rate)
        seed = validate_seed(seed)

        from core.prompt_bypass import generate_with_bypass

        def _submit(**kw):
            return self.client.create_video(**kw)

        task, rewritten = generate_with_bypass(
            _submit, self.client, prompt,
            width=width, height=height, num_frames=num_frames,
            frame_rate=frame_rate, image=image,
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps, extra_body=extra_body,
        )
        if rewritten:
            prompt = rewritten
        task_id = task.get("task_id") or task.get("id")
        video_id = _clean_video_id(task.get("video_id", ""))

        # 必须有 video_id 才能查询，否则无法正确轮询
        if not video_id:
            raise RuntimeError(
                f"视频任务创建成功但未返回 video_id，无法轮询状态。"
                f"task_id={task_id}，请联系支持或用 video_id 查询。"
            )

        # 使用 wait_for_video（超时不抛异常）或 poll_video（超时抛异常）
        if timeout is not None:
            result = self.client.wait_for_video(
                video_id=video_id,
                timeout=timeout,
                interval=SETTINGS.video_poll_interval,
                on_progress=on_progress,
            )
        else:
            result = self.client.poll_video(
                video_id=video_id,
                interval=SETTINGS.video_poll_interval,
                max_wait=SETTINGS.video_max_wait,
                on_progress=on_progress,
            )

        timed_out = result.pop("_timed_out", False)
        # 提取视频URL：remixed_from_video_id 是视频完成后的下载URL
        video_url = result.get("remixed_from_video_id") or result.get("video_url", "")
        local_path = ""
        if video_url and video_url.startswith("http") and not timed_out:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = str(OUTPUT_DIR / "videos" / f"vid_{ts}.mp4")
            with contextlib.suppress(RuntimeError):
                self.client.download_video(video_url, local_path)

        ret = {"url": video_url, "local_path": local_path, "task_id": task_id,
               "video_id": video_id, "model": "agnes-video-v2.0", "prompt": prompt, "num_frames": num_frames}
        if timed_out:
            ret["status"] = "timeout"
            ret["progress"] = result.get("progress", 0)
        return ret

    # 保留旧方法名作为兼容别名
    def _submit_and_wait(self, *args, **kwargs):
        """[已弃用] 请使用 submit_and_wait()"""
        return self.submit_and_wait(*args, **kwargs)

    def text_to_video(self, prompt, width=1152, height=768, num_frames=121,
                      frame_rate=24, negative_prompt=None, seed=None,
                      num_inference_steps=40, on_progress=None,
                      timeout=None) -> dict:
        return self.submit_and_wait(prompt=prompt, width=width, height=height,
            num_frames=num_frames, frame_rate=frame_rate,
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps,
            on_progress=on_progress, timeout=timeout)

    def image_to_video(self, prompt, image_url, width=1152, height=768,
                       num_frames=121, frame_rate=24, negative_prompt=None,
                       seed=None, num_inference_steps=40, on_progress=None,
                       timeout=None) -> dict:
        return self.submit_and_wait(prompt=prompt, width=width, height=height,
            num_frames=num_frames, frame_rate=frame_rate, image=image_url,
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps,
            on_progress=on_progress, timeout=timeout)

    def multi_image_video(self, prompt, image_urls, width=1152, height=768,
                          num_frames=121, frame_rate=24, negative_prompt=None,
                          seed=None, num_inference_steps=40, on_progress=None,
                          timeout=None) -> dict:
        urls = validate_image_urls(image_urls)
        return self.submit_and_wait(prompt=prompt, width=width, height=height,
            num_frames=num_frames, frame_rate=frame_rate, extra_body={"image": urls},
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps,
            on_progress=on_progress, timeout=timeout)

    def keyframe_animation(self, prompt, image_urls, width=1152, height=768,
                           num_frames=121, frame_rate=24, negative_prompt=None,
                           seed=None, num_inference_steps=40, on_progress=None,
                           timeout=None) -> dict:
        urls = validate_image_urls(image_urls)
        return self.submit_and_wait(prompt=prompt, width=width, height=height,
            num_frames=num_frames, frame_rate=frame_rate,
            extra_body={"image": urls, "mode": "keyframes"},
            negative_prompt=negative_prompt, seed=seed,
            num_inference_steps=num_inference_steps,
            on_progress=on_progress, timeout=timeout)
