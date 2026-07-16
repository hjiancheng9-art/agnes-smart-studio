"""Vision tool — standalone image understanding for AI agent consumption.

Usage:
    from core.vision_tool import analyze_image
    result = analyze_image("path/to/image.png", "这张图里有什么？")
"""

from __future__ import annotations


def analyze_image(image_path: str, question: str = "描述这张图片") -> str:
    """Analyze an image and return a text description.

    Tries Zhipu GLM-4V-Flash first (free, capable), falls back to Agnes 1.5-flash.

    Args:
        image_path: Local file path or HTTP URL to the image.
        question: What to ask about the image. Defaults to general description.

    Returns:
        Text description/answer from the vision model.
    """
    if not question.strip():
        question = "描述这张图片"

    # Resolve image source
    try:
        from utils.image_input import load_image_as_url_or_data

        url = load_image_as_url_or_data(image_path)
    except (ValueError, OSError) as e:
        return f"(无法加载图片: {e})"

    # Use provider-aware routing via model registry — unified with chat_vision
    from core.provider import get_capability_info, get_provider_manager, get_vision_models

    mgr = get_provider_manager()
    for model_id in get_vision_models():
        info = get_capability_info(model_id)
        if not info or not info.provider_id:
            continue
        try:
            vc = mgr.create_client(info.provider_id)
            result = vc.chat_multimodal(
                text=question,
                image_url=url,
                model=model_id,
                temperature=0.3,
                max_tokens=1024,
            )
            raw = result["choices"][0]["message"]["content"] or ""
            # Detect content rejection
            rejected = any(phrase in raw for phrase in ("超出", "能力范围", "无法", "不支持"))
            if rejected:
                continue
            return raw
        except (RuntimeError, OSError, ValueError, KeyError, IndexError, ImportError):
            continue
    return "(视觉模型均不可用，请稍后重试)"


def _get_zhipu_client():
    """Get Zhipu vision client (GLM-4V-Flash)."""
    from core.client import CruxClient
    from core.provider import get_provider_manager

    mgr = get_provider_manager()
    zhipu_p = mgr.providers.get("zhipu", {})
    api_key = zhipu_p.get("api_key") or ""
    base_url = zhipu_p.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
    if not api_key:
        import os

        api_key = os.getenv("ZHIPU_API_KEY", "")
    if not api_key:
        raise RuntimeError("Zhipu API key not configured")
    return CruxClient(api_key=api_key, base_url=base_url), "glm-4v-flash"


def _get_agnes_client():
    """Get Agnes (CRUX) vision client."""
    from core.client import CruxClient
    from core.config import CRUX_VISION_BASE_URL

    crux_key = ""
    try:
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        crux_p = mgr.providers.get("crux", {})
        crux_key = crux_p.get("api_key") or ""
    except (ImportError, OSError):
        pass
    if not crux_key:
        import os

        crux_key = os.getenv("CRUX_API_KEY", "") or os.getenv("AGNES_API_KEY", "")
    if not crux_key:
        raise RuntimeError("CRUX API key not configured")
    return CruxClient(api_key=crux_key, base_url=CRUX_VISION_BASE_URL), "agnes-2.0-flash"
