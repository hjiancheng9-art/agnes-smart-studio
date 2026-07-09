"""MCP Client — MCP 网格编译客户端

包装 MCP 工具调用，提供统一的编译请求接口。
当前为 stub 实现，可通过环境变量或配置文件切换真实端点。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional


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


class MCPClient:
    """MCP 网格编译客户端"""

    def __init__(self, endpoint: str | None = None, timeout: float = 10.0):
        """
        Args:
            endpoint: MCP 端点 URL。None 时从环境变量 COMPILER_MCP_ENDPOINT 读取
            timeout: 请求超时（秒）
        """
        self.endpoint = endpoint or os.environ.get("COMPILER_MCP_ENDPOINT", "")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """MCP 是否可连接"""
        if not self.endpoint:
            return False
        return self._ping()

    def compile(self, prompt: str, task_type: str = "",
                style: list[str] | None = None,
                **kwargs) -> dict[str, Any]:
        """通过 MCP 编译需求

        Returns:
            dict with keys: success, workflow, blueprint_used, error

        Raises:
            MCPUnavailableError: MCP 不可用
            MCPTimeoutError: 请求超时
            MCPInvalidWorkflowError: 返回非法 workflow
        """
        if not self.endpoint:
            raise MCPUnavailableError("MCP endpoint 未配置")

        payload = {
            "prompt": prompt,
            "task_type": task_type,
            "style": style or [],
            **kwargs,
        }

        try:
            return self._do_request(payload)
        except MCPError:
            raise
        except Exception as e:
            raise MCPUnavailableError(f"MCP 请求失败: {e}")

    def _ping(self) -> bool:
        """检查 MCP 是否可达"""
        if not self.endpoint:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.endpoint}/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _do_request(self, payload: dict) -> dict:
        """实际的 HTTP 请求"""
        import httpx
        try:
            resp = httpx.post(
                f"{self.endpoint}/compile",
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            raise MCPTimeoutError(f"MCP 请求超时 ({self.timeout}s)")
        except httpx.ConnectError:
            raise MCPUnavailableError(f"无法连接 MCP 端点: {self.endpoint}")
        except Exception as e:
            raise MCPUnavailableError(f"MCP 请求异常: {e}")

        if resp.status_code != 200:
            raise MCPUnavailableError(f"MCP 返回状态码 {resp.status_code}")

        try:
            data = resp.json()
        except Exception:
            raise MCPInvalidWorkflowError("MCP 返回非 JSON 响应")

        if not isinstance(data, dict):
            raise MCPInvalidWorkflowError("MCP 返回非 dict 响应")

        workflow = data.get("workflow", data)
        if isinstance(workflow, dict) and len(workflow) > 0:
            # 验证是否有 class_type
            has_ct = any(
                isinstance(v, dict) and "class_type" in v
                for v in workflow.values()
            )
            if not has_ct:
                raise MCPInvalidWorkflowError("MCP 返回的 workflow 缺少 class_type")

        return data
