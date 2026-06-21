"""文生图引擎"""
import base64
from datetime import datetime
from core.client import AgnesClient
from core.config import OUTPUT_DIR
from core.validator import validate_image_size, validate_model, validate_seed

__all__ = ['TextToImageEngine']



class TextToImageEngine:
    def __init__(self, client: AgnesClient):
        self.client = client

    def generate(self, prompt: str, model: str = "agnes-image-2.1-flash",
                 size: str = "1024x768", seed: int | None = None,
                 negative_prompt: str | None = None,
                 return_url: bool = False) -> dict:
        """生成图片（自动绕过内容过滤）"""
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
            _gen, self.client, prompt,
            model=model, size=size, seed=seed,
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

        return {"url": image_url, "local_path": local_path, "model": model, "prompt": prompt, "size": size, "seed": seed}

    def generate_batch(self, prompts: list[str], model: str = "agnes-image-2.1-flash",
                       size: str = "1024x768", seed: int | None = None) -> list[dict]:
        """批量生成。每张用独立 seed（否则同 prompt+seed 只出一张重复图）。

        seed 给定时作为基准，每张递增 1，保证各不相同。
        """
        results = []
        for i, p in enumerate(prompts):
            s = None if seed is None else validate_seed(seed + i)
            results.append(self.generate(p, model, size, seed=s))
        return results
