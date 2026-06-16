"""文生图引擎"""
import base64
from datetime import datetime
from core.client import AgnesClient
from core.config import OUTPUT_DIR
from core.validator import validate_image_size, validate_model, validate_seed


class TextToImageEngine:
    def __init__(self, client: AgnesClient):
        self.client = client

    def generate(self, prompt: str, model: str = "agnes-image-2.1-flash",
                 size: str = "1024x768", seed: int | None = None,
                 negative_prompt: str | None = None,
                 return_url: bool = False) -> dict:
        """生成图片

        Args:
            return_url: True 时返回 CDN URL（流水线需要传给视频API）；
                        False 时用 b64_json 解码保存本地（避免CDN 401）
        """
        size = validate_image_size(size)
        validate_model(model, "image")
        seed = validate_seed(seed)

        result = self.client.create_image(
            prompt=prompt, model=model, size=size, seed=seed,
            negative_prompt=negative_prompt,
            return_base64=not return_url,
        )
        try:
            item = result["data"][0]
        except (KeyError, IndexError):
            raise RuntimeError(f"图像API返回格式异常: {str(result)[:200]}")

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
            except Exception:
                local_path = ""
        else:
            raise RuntimeError(f"图像API未返回图片数据: {str(result)[:200]}")

        return {"url": image_url, "local_path": local_path, "model": model, "prompt": prompt, "size": size, "seed": seed}

    def generate_batch(self, prompts: list[str], model: str = "agnes-image-2.1-flash",
                       size: str = "1024x768", seed: int | None = None) -> list[dict]:
        return [self.generate(p, model, size, seed) for p in prompts]
