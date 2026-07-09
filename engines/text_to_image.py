"""文生图引擎"""

import asyncio
import base64
from datetime import datetime

from core.async_client import AsyncCruxClient
from core.client import CruxClient
from core.config import OUTPUT_DIR
from core.validator import validate_image_size, validate_model, validate_seed

__all__ = ["TextToImageEngine", "AsyncTextToImageEngine"]


class TextToImageEngine:
    def __init__(self, client: CruxClient):
        self.client = client

    def _get_model(self, model: str = "") -> str:
        """获取图像生成模型，优先用活跃供应商的模型。"""
        if model:
            return model
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            active = mgr.get_active_models()
            return active.get("image", "agnes-image-2.1-flash")
        except Exception:
            return "agnes-image-2.1-flash"

    def generate(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x768",
        seed: int | None = None,
        negative_prompt: str | None = None,
        return_url: bool = False,
    ) -> dict:
        """生成图片（自动绕过内容过滤）"""
        model = self._get_model(model)
        size = validate_image_size(size)
        validate_model(model, "image")
        seed = validate_seed(seed)

        from core.prompt_bypass import generate_with_bypass

        def _gen(**kw):
            r = self.client.create_image(**kw)
            if "data" not in r or not r["data"]:
                raise RuntimeError(f"图像API返回格式异常: {str(r)[:200]}")
            return r

        result, rewritten = generate_with_bypass(
            _gen,
            self.client,
            prompt,
            model=model,
            size=size,
            seed=seed,
            negative_prompt=negative_prompt,
            return_base64=not return_url,
        )
        if rewritten:
            prompt = rewritten
        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图像API返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"t2i_{ts}.png")
        image_url = ""

        if item.get("b64_json"):
            with open(local_path, "wb") as f:
                f.write(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            image_url = item["url"]
            try:
                self.client.download_image(image_url, local_path)
            except (OSError, RuntimeError):
                local_path = ""
        else:
            raise RuntimeError(f"图像API未返回图片数据: {str(result)[:200]}")

        return {
            "url": image_url,
            "local_path": local_path,
            "model": model,
            "prompt": prompt,
            "size": size,
            "seed": seed,
        }

    def generate_batch(
        self, prompts: list[str], model: str = "", size: str = "1024x768", seed: int | None = None
    ) -> list[dict]:
        """批量生成。每张用独立 seed（否则同 prompt+seed 只出一张重复图）。

        seed 给定时作为基准，每张递增 1，保证各不相同。
        """
        results = []
        for i, p in enumerate(prompts):
            s = None if seed is None else validate_seed(seed + i)
            results.append(self.generate(p, model, size, seed=s))
        return results


class AsyncTextToImageEngine:
    """AsyncTextToImageEngine：TextToImageEngine 的 asyncio 原生异步对应物。

    关键差异：generate_batch 使用 asyncio.gather 实现真正的并行图像生成，
    多张图同时请求 API，而非顺序等待。
    """

    def __init__(self, client: AsyncCruxClient):
        self.client = client

    def _get_model(self, model: str = "") -> str:
        if model:
            return model
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_active_models().get("image", "agnes-image-2.1-flash")
        except Exception:
            return "agnes-image-2.1-flash"

    async def generate(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x768",
        seed: int | None = None,
        negative_prompt: str | None = None,
        return_url: bool = False,
    ) -> dict:
        """异步生成图片（自动绕过内容过滤）"""
        model = self._get_model(model)
        size = validate_image_size(size)
        validate_model(model, "image")
        seed = validate_seed(seed)

        from core.prompt_bypass import async_generate_with_bypass

        async def _gen(**kw):
            r = await self.client.create_image(**kw)
            if "data" not in r or not r["data"]:
                raise RuntimeError(f"图像API返回格式异常: {str(r)[:200]}")
            return r

        result, rewritten = await async_generate_with_bypass(
            _gen,
            self.client,
            prompt,
            model=model,
            size=size,
            seed=seed,
            negative_prompt=negative_prompt,
            return_base64=not return_url,
        )
        if rewritten:
            prompt = rewritten
        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图像API返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"t2i_{ts}.png")
        image_url = ""

        if item.get("b64_json"):
            # 文件写入放线程池，避免阻塞事件循环
            await asyncio.to_thread(_write_b64_file, local_path, item["b64_json"])
        elif item.get("url"):
            image_url = item["url"]
            try:
                await self.client.download_image(image_url, local_path)
            except (OSError, RuntimeError):
                local_path = ""
        else:
            raise RuntimeError(f"图像API未返回图片数据: {str(result)[:200]}")

        return {
            "url": image_url,
            "local_path": local_path,
            "model": model,
            "prompt": prompt,
            "size": size,
            "seed": seed,
        }

    async def generate_batch(
        self, prompts: list[str], model: str = "", size: str = "1024x768", seed: int | None = None
    ) -> list[dict]:
        """异步批量生成 — 🎯 并行化核心。

        使用 asyncio.gather 同时发起所有图像生成请求，而非顺序等待。
        每张用独立 seed（否则同 prompt+seed 只出一张重复图）。
        seed 给定时作为基准，每张递增 1，保证各不相同。
        """
        tasks = []
        for i, p in enumerate(prompts):
            s = None if seed is None else validate_seed(seed + i)
            tasks.append(self.generate(p, model, size, seed=s))
        # 🎯 并行：所有图像生成同时进行
        return await asyncio.gather(*tasks)


def _write_b64_file(path: str, b64_data: str) -> None:
    """线程安全的 base64 文件写入（供 asyncio.to_thread 调用）"""
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64_data))
