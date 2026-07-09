"""
ComfyFlow HTTP Client — CRUX 通过 HTTP 远程调用 ComfyFlow Compiler

不 import comfyflow_compiler 的任何模块。
不直接写 CodeBuddy/comfyui智能体 项目文件。
纯 HTTP 调用 http://127.0.0.1:8080/{health|probe|compile}
"""

from __future__ import annotations

import os
from typing import Any

try:
    import httpx as _httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

    # Fallback: use urllib if httpx not available
    import json
    import urllib.request
    import urllib.error


class ComfyFlowError(Exception):
    """ComfyFlow API 调用异常"""
    pass


class ComfyFlowClient:
    """ComfyFlow API 的 HTTP 客户端

    使用方式:
        client = ComfyFlowClient()
        health = client.health()
        result = client.compile("a cat")
        probe = client.probe()
    """

    def __init__(self, base_url: str | None = None, timeout: int = 60):
        self.base_url = (base_url or os.environ.get(
            "COMFYFLOW_API_URL", "http://127.0.0.1:8080"
        )).rstrip("/")
        self.timeout = timeout

    # ── health ──────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        """GET /health"""
        return self._get("/health")

    # ── probe ───────────────────────────────────────────

    def probe(self) -> dict[str, Any]:
        """GET /probe"""
        return self._get("/probe")

    # ── compile ─────────────────────────────────────────

    def compile(self, prompt: str, task_type: str = "txt2img") -> dict[str, Any]:
        """POST /compile"""
        return self._post("/compile", json={"prompt": prompt, "task_type": task_type})

    # ── HTTP 底层 ───────────────────────────────────────

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if HAS_HTTPX:
            with _httpx.Client(timeout=self.timeout) as c:
                resp = c.get(url)
                return self._wrap(resp)
        else:
            return self._urllib_request("GET", url)

    def _post(self, path: str, json: dict) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if HAS_HTTPX:
            with _httpx.Client(timeout=self.timeout) as c:
                resp = c.post(url, json=json)
                return self._wrap(resp)
        else:
            return self._urllib_request("POST", url, json)

    def _wrap(self, resp: Any) -> dict[str, Any]:
        """统一封装 httpx 或 urllib 的响应"""
        try:
            data = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            data = {"raw_text": resp.text if hasattr(resp, "text") else str(resp)}

        if not isinstance(data, dict):
            data = {"data": data}

        status = getattr(resp, "status_code", 0)
        data.setdefault("http_status", status)
        data.setdefault("ok", getattr(resp, "is_success", status in (200, 201)))
        data.setdefault("success", bool(data.get("success", data.get("ok", False))))

        if not data.get("ok") and not data.get("success"):
            data.setdefault("error", f"HTTP {status}")

        return data

    def _urllib_request(self, method: str, url: str, body: dict | None = None) -> dict[str, Any]:
        import json, urllib.request

        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                body_data = json.loads(resp.read().decode())
                return {
                    "http_status": status,
                    "ok": status in (200, 201),
                    "success": body_data.get("success", status in (200, 201)),
                    **body_data,
                }
        except urllib.error.HTTPError as e:
            return {
                "http_status": e.code,
                "ok": False,
                "success": False,
                "error": f"HTTP {e.code}: {e.reason}",
            }
        except Exception as e:
            return {
                "http_status": 0,
                "ok": False,
                "success": False,
                "error": str(e),
            }


def get_client() -> ComfyFlowClient:
    """快捷获取客户端实例"""
    return ComfyFlowClient()
