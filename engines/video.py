"""视频生成引擎 - 4种模式 + 异步轮询 + 进度防回退 + 双通道查询"""
from datetime import datetime
from core.client import AgnesClient
from core.config import OUTPUT_DIR, SETTINGS
from core.validator import validate_num_frames, validate_frame_rate, validate_seed, validate_image_urls, validate_video_resolution


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
        video_id = task.get("video_id", "")
        return {"task_id": task_id, "video_id": video_id, "status": "submitted",
                "model": "agnes-video-v2.0", "prompt": prompt, "num_frames": num_frames}

    def submit_and_wait(self, prompt, width=1152, height=768, num_frames=121,
                        frame_rate=24, image=None, negative_prompt=None,
                        seed=None, num_inference_steps=40, extra_body=None,
                        on_progress=None, timeout=None) -> dict:
        """提交视频任务并限时等待。timeout=None 使用配置默认值，超时返回当前状态。"""
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
        video_id = task.get("video_id", "")

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
            try:
                self.client.download_video(video_url, local_path)
            except RuntimeError:
                pass

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
