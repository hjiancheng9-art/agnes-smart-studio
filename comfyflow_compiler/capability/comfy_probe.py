"""ComfyProbe — 真实 ComfyUI 运行时探测

通过 HTTP API 探测 ComfyUI 的真实运行状态。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Optional

from .errors import ComfyOfflineError


class ComfyProbeError(Exception):
    """探测失败"""
    pass


MODEL_FOLDERS = [
    "checkpoints", "loras", "vae", "clip", "unet",
    "style_models", "upscale_models", "hypernetworks",
    "controlnet", "gligen", "animated_models",
]


class ComfyProbe:
    """ComfyUI 运行时探测"""

    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def probe_all(self) -> dict[str, Any]:
        """完整探测：健康、节点、模型、队列"""
        return {
            "online": self.check_online(),
            "version": self.get_version(),
            "nodes": self.get_nodes(),
            "models": self.get_all_models(),
            "queue": self.get_queue(),
            "system": self.get_system_stats(),
        }

    def check_online(self) -> bool:
        """ComfyUI 是否在线"""
        try:
            self._get("/")
            return True
        except Exception:
            return False

    def get_version(self) -> str:
        """获取 ComfyUI 版本"""
        try:
            data = self._get_json("/")
            return data.get("version", data.get("comfy_version", ""))
        except Exception:
            return ""

    def get_nodes(self) -> dict[str, Any]:
        """获取所有可用节点信息"""
        try:
            return self._get_json("/object_info")
        except Exception:
            return {}

    def get_models(self, folder: str) -> list[str]:
        """获取指定模型目录的模型列表"""
        try:
            data = self._get_json(f"/models/{folder}")
            if isinstance(data, dict):
                return data.get("models", [])
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def get_all_models(self) -> dict[str, list[str]]:
        """获取所有模型"""
        result = {}
        for folder in MODEL_FOLDERS:
            try:
                models = self.get_models(folder)
                if models:
                    result[folder] = models
            except Exception:
                pass
        return result

    def get_queue(self) -> dict:
        """获取队列状态"""
        try:
            return self._get_json("/queue")
        except Exception:
            return {}

    def get_system_stats(self) -> dict:
        """获取系统状态"""
        try:
            return self._get_json("/system_stats")
        except Exception:
            return {}

    def check_node_exists(self, class_type: str) -> bool:
        """检查节点是否可用"""
        nodes = self.get_nodes()
        return class_type in nodes

    def check_model_exists(self, model_name: str, folder: str = "checkpoints") -> bool:
        """检查模型是否存在"""
        models = self.get_models(folder)
        return any(model_name in m for m in models)

    def _get(self, path: str) -> bytes:
        """原始 GET 请求"""
        try:
            req = urllib.request.Request(f"{self.base_url}{path}")
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            return resp.read()
        except urllib.error.URLError as e:
            raise ComfyOfflineError(f"ComfyUI 不可达 ({self.base_url}): {e}")
        except Exception as e:
            raise ComfyProbeError(f"探测失败 {path}: {e}")

    def _get_json(self, path: str) -> Any:
        """GET 并解析 JSON"""
        data = self._get(path)
        return json.loads(data)
