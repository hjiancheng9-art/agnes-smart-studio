"""Vision bridge — agnes-2.0-flash vision model integration with language model."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("crux.vision")


def _vision_fallback(self, text: str, image_url: str) -> str:
    """Vision understanding via agnes-2.0-flash. Simple retry on failure."""
    model_id = self.vision_model or "agnes-2.0-flash"
    complexity, max_tok = self._classify_vision_complexity(text)
    vision_text = f"请仔细观察图片，逐步推理分析：\n{text}" if complexity == "complex" else text

    for attempt in range(2):
        try:
            from core.provider import get_capability_info, get_provider_manager

            mgr = get_provider_manager()
            info = get_capability_info(model_id)
            vc = mgr.create_client(info.provider_id) if (info and info.provider_id) else self.vision_client

            r = vc.chat_multimodal(text=vision_text, image_url=image_url, model=model_id, max_tokens=max_tok)
            content = r["choices"][0]["message"]["content"] or ""
            try:
                from core.cost_tracker import record_usage

                record_usage(model=model_id, kind="text", usage=r.get("usage"), label="vision")
            except (ImportError, OSError, KeyError, TypeError):
                pass
            return content
        except (httpx.HTTPStatusError, OSError, TimeoutError, KeyError, IndexError, RuntimeError) as e:
            logger.warning("vision call attempt %d failed for %s: %s", attempt + 1, model_id, e)
            if attempt < 1:
                import time as _time

                _time.sleep(2)
            else:
                return f"(视觉理解失败: {type(e).__name__})\n建议：检查 CRUX_API_KEY 是否配置正确。"

    return "(视觉理解失败: 未知错误)"
