"""Prompt模板库 - 内置风格模板 + 自定义模板"""

from core.config import PROMPT_TEMPLATES

__all__ = ['apply_template', 'get_template', 'get_template_info', 'list_templates']



def list_templates() -> list[str]:
    """列出所有可用模板名"""
    return list(PROMPT_TEMPLATES.keys())


def get_template(name: str) -> dict | None:
    """获取指定模板"""
    return PROMPT_TEMPLATES.get(name)


def apply_template(name: str, user_prompt: str, target: str = "image") -> tuple[str, str]:
    """将模板应用到用户Prompt

    Args:
        name: 模板名
        user_prompt: 用户原始描述
        target: "image" 或 "video"
    Returns:
        (enhanced_prompt, negative_prompt)
    """
    tpl = get_template(name)
    if not tpl:
        return user_prompt, ""

    style_prompt = tpl.get(target, tpl.get("image", ""))
    negative = tpl.get("negative", "")

    enhanced = f"{user_prompt}, {style_prompt}" if style_prompt else user_prompt

    return enhanced, negative


def get_template_info(name: str) -> str:
    """获取模板的简要描述"""
    tpl = get_template(name)
    if not tpl:
        return f"未找到模板: {name}"

    lines = [f"[bold cyan]{name}[/]"]
    for key in ("image", "video", "negative"):
        if key in tpl:
            label = {"image": "图片", "video": "视频", "negative": "负向"}.get(key, key)
            lines.append(f"  {label}: {tpl[key][:60]}...")
    return "\n".join(lines)
