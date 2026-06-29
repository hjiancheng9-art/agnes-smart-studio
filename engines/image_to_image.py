"""图生图/编辑/多图合成引擎 - 基于 agnes-image-2.1-flash"""

from datetime import datetime

from core.async_client import AsyncCruxClient
from core.client import CruxClient
from core.config import OUTPUT_DIR
from core.validator import validate_image_size, validate_image_urls, validate_model, validate_seed

__all__ = ["ImageToImageEngine", "AsyncImageToImageEngine"]


class ImageToImageEngine:
    """图生图引擎 - image 通过 extra_body 传入以触发图生图模式"""

    def __init__(self, client: CruxClient):
        self.client = client

    def edit(
        self,
        prompt: str,
        image_urls: str | list[str],
        size: str = "1024x768",
        seed: int | None = None,
        model: str = "agnes-image-2.1-flash",
    ) -> dict:
        """图生图/编辑 - 单图或多图编辑"""
        size = validate_image_size(size)
        validate_model(model, "image")
        seed = validate_seed(seed)
        urls = validate_image_urls(image_urls)

        result = self.client.create_image(
            prompt=prompt,
            model=model,
            size=size,
            seed=seed,
            extra_body={"image": urls},
        )

        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图生图API返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"i2i_{ts}.png")
        image_url = item.get("url", "")

        if image_url:
            self.client.download_image(image_url, local_path)
        else:
            raise RuntimeError(f"图生图API未返回URL: {str(result)[:200]}")

        return {"url": image_url, "local_path": local_path, "model": model, "prompt": prompt, "source_images": urls}

    def compose(self, prompt: str, image_urls: list[str], size: str = "1024x768", seed: int | None = None) -> dict:
        """多图合成 - 融合多张图元素"""
        return self.edit(prompt=prompt, image_urls=image_urls, size=size, seed=seed, model="agnes-image-2.1-flash")

    def style_transfer(self, prompt: str, image_url: str, size: str = "1024x768", seed: int | None = None) -> dict:
        """风格迁移 - 保持构图改风格"""
        return self.edit(prompt=prompt, image_urls=[image_url], size=size, seed=seed, model="agnes-image-2.1-flash")

    def edit_with_21(self, prompt: str, image_urls: str | list[str], size: str = "1024x768") -> dict:
        """使用 2.1-flash 图生图（高密度优化）"""
        urls = validate_image_urls(image_urls)
        result = self.client.create_image(
            prompt=prompt,
            model="agnes-image-2.1-flash",
            size=size,
            extra_body={"image": urls},
        )
        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图生图API(2.1)返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"i2i_hd_{ts}.png")
        image_url = item.get("url", "")

        if image_url:
            self.client.download_image(image_url, local_path)
        else:
            raise RuntimeError(f"图生图API(2.1)未返回URL: {str(result)[:200]}")

        return {"url": image_url, "local_path": local_path, "model": "agnes-image-2.1-flash", "prompt": prompt}


class AsyncImageToImageEngine:
    """AsyncImageToImageEngine：ImageToImageEngine 的 asyncio 原生异步对应物。

    关键差异：所有 I/O 点（create_image / download_image）改为 await。
    业务逻辑（参数校验、结果解析）与同步版完全一致。
    """

    def __init__(self, client: AsyncCruxClient):
        self.client = client

    async def edit(
        self,
        prompt: str,
        image_urls: str | list[str],
        size: str = "1024x768",
        seed: int | None = None,
        model: str = "agnes-image-2.1-flash",
    ) -> dict:
        """异步图生图/编辑 - 单图或多图编辑"""
        size = validate_image_size(size)
        validate_model(model, "image")
        seed = validate_seed(seed)
        urls = validate_image_urls(image_urls)

        result = await self.client.create_image(
            prompt=prompt,
            model=model,
            size=size,
            seed=seed,
            extra_body={"image": urls},
        )

        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图生图API返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"i2i_{ts}.png")
        image_url = item.get("url", "")

        if image_url:
            await self.client.download_image(image_url, local_path)
        else:
            raise RuntimeError(f"图生图API未返回URL: {str(result)[:200]}")

        return {"url": image_url, "local_path": local_path, "model": model, "prompt": prompt, "source_images": urls}

    async def compose(
        self, prompt: str, image_urls: list[str], size: str = "1024x768", seed: int | None = None
    ) -> dict:
        """异步多图合成 - 融合多张图元素"""
        return await self.edit(
            prompt=prompt,
            image_urls=image_urls,
            size=size,
            seed=seed,
            model="agnes-image-2.1-flash",
        )

    async def style_transfer(
        self, prompt: str, image_url: str, size: str = "1024x768", seed: int | None = None
    ) -> dict:
        """异步风格迁移 - 保持构图改风格"""
        return await self.edit(
            prompt=prompt,
            image_urls=[image_url],
            size=size,
            seed=seed,
            model="agnes-image-2.1-flash",
        )

    async def edit_with_21(self, prompt: str, image_urls: str | list[str], size: str = "1024x768") -> dict:
        """异步使用 2.1-flash 图生图（高密度优化）"""
        urls = validate_image_urls(image_urls)
        result = await self.client.create_image(
            prompt=prompt,
            model="agnes-image-2.1-flash",
            size=size,
            extra_body={"image": urls},
        )
        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图生图API(2.1)返回格式异常: {str(result)[:200]}") from None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = str(OUTPUT_DIR / "images" / f"i2i_hd_{ts}.png")
        image_url = item.get("url", "")

        if image_url:
            await self.client.download_image(image_url, local_path)
        else:
            raise RuntimeError(f"图生图API(2.1)未返回URL: {str(result)[:200]}")

        return {"url": image_url, "local_path": local_path, "model": "agnes-image-2.1-flash", "prompt": prompt}
