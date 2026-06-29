"""智能工作流 - 一站式流水线、分镜脚本、批量生成"""

import base64
from pathlib import Path

from core.brain import SmartBrain
from core.client import CruxClient
from engines.image_to_image import ImageToImageEngine
from engines.text_to_image import TextToImageEngine
from engines.video import VideoEngine

__all__ = ["PipelineOrchestrator"]


def _local_image_to_b64_url(path: str) -> str:
    """将本地图片文件转为纯 base64 字符串（视频 API 后备方案）

    注意：视频 API image 字段优先使用 URL，base64 作为后备。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    return base64.b64encode(p.read_bytes()).decode()


class PipelineOrchestrator:
    """流水线编排器 - 协调多引擎完成复杂工作流"""

    def __init__(self, client: CruxClient):
        self.client = client
        self.brain = SmartBrain(client)
        self.t2i = TextToImageEngine(client)
        self.i2i = ImageToImageEngine(client)
        self.video = VideoEngine(client)

    def text_to_image_to_video(
        self,
        prompt: str,
        style: str | None = None,
        image_size: str = "1024x768",
        video_width: int = 1152,
        video_height: int = 768,
        num_frames: int = 121,
        frame_rate: int = 24,
        enhance: bool = True,
        submit_only: bool = False,
        num_inference_steps: int = 40,
        timeout: float | None = 120.0,
        on_image_done=None,
        on_video_progress=None,
    ) -> dict:
        """一站式：文本 → 图片 → 视频

        Args:
            prompt: 用户原始描述
            style: 可选风格模板名
            enhance: 是否用Brain增强Prompt
            submit_only: 仅提交视频任务，不等待完成
            num_inference_steps: 视频推理步数(20-50，默认40)
            timeout: 视频轮询超时秒数，None使用配置默认值
            on_image_done: 图片生成完成回调
            on_video_progress: 视频进度回调
        Returns:
            {"image": {...}, "video": {...}}
        """
        # Step 1: 增强Prompt
        if enhance:
            img_result = self.brain.enhance_image_prompt(prompt, style)
            img_prompt = img_result.get("optimized_prompt", prompt)
            neg = img_result.get("negative_prompt", "")
        else:
            img_prompt = prompt
            neg = ""

        # Step 2: 生成图片（流水线用 URL 模式，视频 API 需要 URL 访问图片）
        image_data = self.t2i.generate(prompt=img_prompt, size=image_size, negative_prompt=neg or None, return_url=True)
        if on_image_done:
            on_image_done(image_data)

        # Step 3: 增强视频Prompt
        if enhance:
            vid_result = self.brain.enhance_video_prompt(prompt)
            vid_prompt = vid_result.get("optimized_prompt", prompt)
            vid_neg = vid_result.get("negative_prompt", neg)
        else:
            vid_prompt = prompt
            vid_neg = neg

        # Step 4: 图片转视频
        # 视频 API 的 image 字段只接受 URL（CDN 直连），不接受 base64
        video_image = image_data.get("url")
        if not video_image:
            raise RuntimeError(
                f"图片未返回 CDN URL，无法传给视频 API。"
                f"请检查 API 配置或网络连接。local_path={image_data.get('local_path')}"
            )
        if submit_only:
            video_data = self.video.submit_only(
                prompt=vid_prompt,
                image=video_image,
                width=video_width,
                height=video_height,
                num_frames=num_frames,
                frame_rate=frame_rate,
                negative_prompt=vid_neg or None,
                num_inference_steps=num_inference_steps,
            )
        else:
            video_data = self.video.image_to_video(
                prompt=vid_prompt,
                image_url=video_image,
                width=video_width,
                height=video_height,
                num_frames=num_frames,
                frame_rate=frame_rate,
                negative_prompt=vid_neg or None,
                num_inference_steps=num_inference_steps,
                on_progress=on_video_progress,
                timeout=timeout,
            )

        return {"image": image_data, "video": video_data}

    def storyboard_to_video(
        self,
        creative_brief: str,
        image_size: str = "1024x768",
        video_width: int = 1152,
        video_height: int = 768,
        frame_rate: int = 24,
        negative_prompt: str | None = None,
        submit_only: bool = False,
        num_inference_steps: int = 40,
        timeout: float | None = 120.0,
        on_scene_done=None,
        on_video_progress=None,
    ) -> dict:
        """分镜脚本：创意描述 → 分镜 → 逐镜生图 → 转视频

        Args:
            creative_brief: 创意概述
            negative_prompt: 负向提示词
            submit_only: 仅提交视频任务，不等待完成
            num_inference_steps: 视频推理步数(20-50，默认40)
            timeout: 视频轮询超时秒数，None使用配置默认值
            on_scene_done: 每个场景完成回调(scene_index, image_data)
            on_video_progress: 最终视频进度回调
        Returns:
            {"storyboard": {...}, "scenes": [...], "final_video": {...}}
        """
        # Step 1: 生成分镜
        storyboard = self.brain.generate_storyboard(creative_brief)
        scenes = storyboard.get("scenes", [])

        if not scenes:
            # 降级为单场景
            scenes = [{"scene": 1, "description": creative_brief, "duration_sec": 5, "image_prompt": creative_brief}]

        # Step 2: 逐镜生成图片
        scene_results = []
        image_urls = []
        for i, scene in enumerate(scenes):
            img_prompt = scene.get("image_prompt", scene.get("description", creative_brief))
            try:
                img_data = self.t2i.generate(
                    prompt=img_prompt, size=image_size, negative_prompt=negative_prompt, return_url=True
                )
                scene_results.append({"scene": scene, "image": img_data})
                img_url = img_data.get("url")
                if img_url:
                    image_urls.append(img_url)
                else:
                    # 无 URL 时跳过该场景（视频 API 不支持 base64）
                    scene_results[-1] = {"scene": scene, "image": img_data, "error": "无CDN URL，无法用于视频"}
                if on_scene_done:
                    on_scene_done(i, img_data)
            except (RuntimeError, OSError, ValueError) as e:
                scene_results.append({"scene": scene, "image": None, "error": str(e)})

        # Step 3: 多图转视频（image 和 mode 放在 extra_body 内）
        video_data = {}
        if image_urls:
            if submit_only:
                video_data = self.video.submit_only(
                    prompt=f"Based on storyboard: {creative_brief}",
                    width=video_width,
                    height=video_height,
                    frame_rate=frame_rate,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    extra_body={"image": image_urls, "mode": "keyframes"},
                )
            else:
                video_data = self.video.multi_image_video(
                    prompt=f"Based on storyboard: {creative_brief}",
                    image_urls=image_urls,
                    width=video_width,
                    height=video_height,
                    frame_rate=frame_rate,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    on_progress=on_video_progress,
                    timeout=timeout,
                )

        return {"storyboard": storyboard, "scenes": scene_results, "final_video": video_data}

    def batch_generate_images(
        self,
        prompts: list[str],
        style: str | None = None,
        size: str = "1024x768",
        enhance: bool = True,
        on_done=None,
    ) -> list[dict]:
        """批量图片生成（含Prompt增强）

        Args:
            prompts: 描述列表
            style: 风格模板
            on_done: 每张完成回调(index, result)
        Returns:
            结果列表
        """
        results = []
        for i, prompt in enumerate(prompts):
            if enhance:
                enhanced = self.brain.enhance_image_prompt(prompt, style)
                final_prompt = enhanced.get("optimized_prompt", prompt)
            else:
                final_prompt = prompt

            try:
                data = self.t2i.generate(prompt=final_prompt, size=size)
                results.append(data)
                if on_done:
                    on_done(i, data)
            except (RuntimeError, OSError, ValueError) as e:
                results.append({"error": str(e), "prompt": prompt})

        return results
