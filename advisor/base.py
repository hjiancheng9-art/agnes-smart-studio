"""
Advisor 层数据契约
==================
定义 AdvisorResult 数据类和 AdvisorClient 协议。
所有 Advisor 实现（CDP、OpenAI API 等）都遵循此接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

AdvisorStatus = Literal[
    "ok",
    "timeout",
    "rate_limited",
    "unavailable",
    "error",
]


@dataclass(frozen=True)
class AdvisorResult:
    """Advisor 查询结果，不可变。"""

    status: AdvisorStatus
    content: str = ""
    source: str = ""  # "cdp_chatgpt" | "openai_api"
    latency_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """是否成功获取到有效回复"""
        return self.status == "ok" and bool(self.content.strip())


class AdvisorClient(Protocol):
    """Advisor 客户端协议 — 所有实现必须满足此接口。

    同步接口，与 CRUX 主链路的同步生成器模式一致。
    """

    def startup(self) -> None:
        """初始化连接，验证后端可用。失败抛异常。"""
        ...

    def ask(self, query: str, context: str = "") -> AdvisorResult:
        """发送查询并返回顾问结果。

        Args:
            query: 用户原始问题
            context: CRUX 上下文（可选）

        Returns:
            AdvisorResult，status 指示成功/超时/不可用等
        """
        ...

    def ask_with_files(self, query: str, file_paths: list[str], context: str = "") -> AdvisorResult:
        """发送查询 + 文件附件并返回顾问结果。

        Args:
            query: 用户问题
            file_paths: 要上传的文件路径列表
            context: CRUX 上下文（可选）

        Returns:
            AdvisorResult
        """
        ...

    def health(self) -> bool:
        """快速健康检查，不阻塞。"""
        ...

    def close(self) -> None:
        """清理资源。"""
        ...
