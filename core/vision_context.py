"""Vision Context — 图片上下文持久化 + 按需重查。

让文本 LLM 在会话中始终能引用视觉情报。
首次看图后持久化描述，后续追问按需调用 vision 模型重查具体问题。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.vision_ctx")


class VisionContext:
    """图片上下文持久化 + 按需重查。

    核心能力：
    1. register() — 注册图片及其初始描述
    2. needs_lookup() — 检测用户是否在引用图片
    3. reask() — 按具体问题重新查询 vision 模型
    """

    def __init__(self) -> None:
        self.image_url: str = ""
        self.last_raw: str = ""
        self.queries: list[dict[str, str]] = []

    @property
    def active(self) -> bool:
        return bool(self.image_url)

    def register(self, image_url: str, vision_raw: str) -> None:
        """注册新图片及其初始描述，覆盖之前的图片上下文。"""
        self.image_url = image_url
        self.last_raw = vision_raw
        self.queries = [{"q": "describe", "a": vision_raw}]
        logger.debug("vision_ctx registered: %.60s", image_url)

    def needs_lookup(self, text: str) -> bool:
        """启发式判断用户是否在引用当前图片。

        关键词匹配 + 短查询检测（低误报率设计）。
        """
        if not self.image_url:
            return False
        text_lower = text.lower().strip()
        # 关键词触发
        keywords = [
            "图片",
            "照片",
            "图",
            "画面",
            "image",
            "picture",
            "photo",
            "左上角",
            "右下角",
            "左下角",
            "右上角",
            "中间",
            "中心",
            "背景",
            "前景",
            "角落",
            "什么颜色",
            "什么东西",
            "什么字",
            "什么内容",
            "什么图案",
            "里面",
            "上面",
            "上面",
            "下面",
            "左边",
            "右边",
            "这个",
            "那个",
            "它",
            "它",
            "this",
            "that",
            "the image",
            "the picture",
            "the photo",
            "what color",
            "what is",
            "describe",
            "how many",
            "where is",
            "can you see",
        ]
        for kw in keywords:
            if kw in text_lower:
                return True
        return False

    def reask(self, question: str, vision_caller: Callable[[str, str], str]) -> str | None:
        """按具体问题重新查询 vision 模型。

        Args:
            question: 用户的具体追问（如"左上角是什么颜色"）
            vision_caller: 接受 (text, image_url) 返回描述的调用函数
        Returns:
            vision 模型的回答，失败时返回 None
        """
        if not self.image_url:
            return None
        try:
            result = vision_caller(question, self.image_url)
            self.queries.append({"q": question, "a": result})
            logger.debug("vision_ctx reask success: %.60s", question)
            return result
        except Exception as e:
            logger.warning("vision_ctx reask failed: %s: %s", type(e).__name__, e)
            return None

    def clear(self) -> None:
        """清除图片上下文。"""
        self.image_url = ""
        self.last_raw = ""
        self.queries = []
