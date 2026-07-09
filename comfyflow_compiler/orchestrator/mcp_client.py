"""MCP Client — MCP 网格编译客户端

真实 HTTP 实现，支持重试、超时、健康检查。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


class MCPError(Exception):
    """MCP 基础异常"""
    pass


class MCPTimeoutError(MCPError):
    """MCP 超时"""
    pass


class MCPUnavailableError(MCPError):
    """MCP 不可用"""
    pass


class MCPInvalidWorkflowError(MCPError):
    """MCP 返回非法 workflow"""
    pass


@dataclass
class CompileRequest:
    """MCP 编译请求"""
    prompt: str
    task_type: str = ""
    style: list[str] = field(default_factory=list)
    blueprint_id: str = ""
    quality_mode: str = "balanced"

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "task_type": self.task_type,
            "style": self.style,
            "blueprint_id": self.blueprint_id,
            "quality_mode": self.quality_mode,
        }


class MCPClient:
    """MCP 网格编译客户端（真实 HTTP）"""

    def __init__(self, endpoint: str | None = None, timeout: float = 10.0,
                 max_retries: int = 2, retry_delay: float = 0.5):
        self.endpoint = endpoint or os.environ.get("COMPILER_MCP_ENDPOINT", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = httpx.Client(timeout=timeout)

    @property
    def available(self) -> bool:
        if not self.endpoint:
            return False
        return self._ping()

    def compile(self, request: CompileRequest | str, **kwargs) -> dict[str, Any]:
        """通过 MCP 编译需求

        Args:
            request: CompileRequest 或纯字符串 prompt

        Returns:
            dict: {"success": bool, "workflow": dict, "blueprint_used": str, "error": str}

        Raises:
            MCPUnavailableError: MCP 不可用
            MCPTimeoutError: 请求超时
            MCPInvalidWorkflowError: 返回非法 workflow
        """
        if isinstance(request, str):
            request = CompileRequest(prompt=request)

        if not self.endpoint:
            raise MCPUnavailableError("MCP endpoint 未配置 (设置 COMPILER_MCP_ENDPOINT 或传入 endpoint)")

        return self._do_request_with_retry(request)

    def _do_request_with_retry(self, request: CompileRequest) -> dict:
        """带重试的请求"""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return self._do_request(request)
            except (MCPTimeoutError, MCPUnavailableError) as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise
            except MCPInvalidWorkflowError:
                # 非法 workflow 不重试
                raise
            except Exception as e:
                last_error = MCPUnavailableError(f"MCP 请求异常: {e}")
                raise last_error

        raise last_error or MCPUnavailableError("MCP 请求失败 (重试耗尽)")

    def _do_request(self, request: CompileRequest) -> dict:
        """实际 HTTP 请求"""
        try:
            resp = self._client.post(
                f"{self.endpoint}/compile",
                json=request.to_dict(),
            )
        except httpx.TimeoutException:
            raise MCPTimeoutError(f"MCP 请求超时 ({self.timeout}s)")
        except httpx.ConnectError:
            raise MCPUnavailableError(f"无法连接 MCP 端点: {self.endpoint}")
        except httpx.RemoteProtocolError as e:
            raise MCPUnavailableError(f"MCP 协议错误: {e}")

        if resp.status_code == 429:
            raise MCPUnavailableError("MCP 限流 (429)")
        if resp.status_code == 404:
            raise MCPUnavailableError("MCP 端点不可用 (404)")
        if resp.status_code >= 500:
            raise MCPUnavailableError(f"MCP 服务端错误 ({resp.status_code})")
        if resp.status_code == 504:
            raise MCPTimeoutError(f"MCP 网关超时 (504)")
        if resp.status_code != 200:
            raise MCPUnavailableError(f"MCP 返回状态码 {resp.status_code}")

        return self._parse_response(resp)

    def _parse_response(self, resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except Exception:
            raise MCPInvalidWorkflowError("MCP 返回非 JSON 响应")

        if not isinstance(data, dict):
            raise MCPInvalidWorkflowError("MCP 返回非 dict 响应")

        workflow = data.get("workflow", data)
        if isinstance(workflow, dict) and workflow:
            has_ct = any(isinstance(v, dict) and "class_type" in v for v in workflow.values())
            if not has_ct:
                raise MCPInvalidWorkflowError("MCP 返回的 workflow 缺少 class_type")

        return data

    def health(self) -> dict:
        """健康检查"""
        if not self.endpoint:
            return {"status": "unconfigured", "endpoint": ""}
        try:
            resp = self._client.get(f"{self.endpoint}/health", timeout=3.0)
            if resp.status_code == 200:
                return {"status": "ok", "endpoint": self.endpoint}
            return {"status": "error", "endpoint": self.endpoint, "code": resp.status_code}
        except Exception as e:
            return {"status": "unavailable", "endpoint": self.endpoint, "error": str(e)}

    def _ping(self) -> bool:
        return self.health().get("status") == "ok"

    def close(self):
        self._client.close()
