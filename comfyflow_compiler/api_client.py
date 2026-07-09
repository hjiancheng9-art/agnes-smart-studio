"""ComfyFlow Compiler — ComfyUI API 客户端

支持 HTTP + WebSocket 双通道：
- POST /prompt 提交工作流
- /ws 实时监听进度
- /history 获取结果
- /object_info 动态获取节点定义
- /upload/image 上传参考图
"""

from __future__ import annotations
import json
import time
import asyncio
import urllib.request
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class ExecutionProgress:
    prompt_id: str = ""
    status: str = "queued"       # queued / running / done / error
    current_node: str = ""
    current_node_class: str = ""
    progress: float = 0.0        # 0-1
    executed_nodes: List[str] = field(default_factory=list)
    output_images: List[str] = field(default_factory=list)
    error: Optional[str] = None


class ComfyAPIClient:
    """
    ComfyUI API 客户端。

    用法:
        client = ComfyAPIClient("http://127.0.0.1:8188")
        prompt_id = client.queue_prompt(workflow_json)
        result = client.wait_for_completion(prompt_id)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    # =========================================================================
    # 核心 API
    # =========================================================================

    def queue_prompt(self, workflow: Dict[str, Any],
                     prompt_id: Optional[str] = None) -> str:
        """提交工作流到执行队列，返回 prompt_id"""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id,
            "prompt_id": prompt_id or str(uuid.uuid4()),
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("prompt_id", payload["prompt_id"])

    def get_history(self, prompt_id: str) -> Optional[Dict]:
        """获取执行历史 / 结果"""
        try:
            req = urllib.request.Request(f"{self.base_url}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            return data.get(prompt_id)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def get_object_info(self) -> Dict[str, Any]:
        """获取所有可用节点的定义（含输入输出类型）"""
        req = urllib.request.Request(f"{self.base_url}/object_info")
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode("utf-8"))

    def get_models(self, folder: str = "checkpoints") -> List[str]:
        """获取指定模型文件夹下的模型列表"""
        req = urllib.request.Request(f"{self.base_url}/models/{folder}")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))

    def upload_image(self, image_path: str | Path,
                     subfolder: str = "") -> Dict[str, Any]:
        """上传参考图到 ComfyUI input 目录"""
        import io
        from urllib.parse import urlencode

        image_path = Path(image_path)
        if not image_path.exists():
            return {"error": f"文件不存在: {image_path}"}

        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
        body = io.BytesIO()

        # image field
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'.encode())
        body.write(b"Content-Type: image/png\r\n\r\n")
        body.write(image_path.read_bytes())
        body.write(b"\r\n")

        # subfolder
        if subfolder:
            body.write(f"--{boundary}\r\n".encode())
            body.write(b'Content-Disposition: form-data; name="subfolder"\r\n\r\n')
            body.write(subfolder.encode())
            body.write(b"\r\n")

        # overwrite
        body.write(f"--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
        body.write(b"true\r\n")
        body.write(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode("utf-8"))

    # =========================================================================
    # WebSocket 实时监听
    # =========================================================================

    def wait_for_completion(self, prompt_id: str,
                            on_progress: Optional[Callable] = None,
                            timeout: int = 300) -> ExecutionProgress:
        """
        通过 WebSocket 实时监听执行进度，直到完成。

        Args:
            prompt_id: 要监听的 prompt_id
            on_progress: 进度回调函数
            timeout: 超时秒数

        Returns:
            ExecutionProgress
        """
        import socket
        import struct

        progress = ExecutionProgress(prompt_id=prompt_id)

        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={self.client_id}"

        try:
            import websocket
            ws = websocket.create_connection(ws_url, timeout=10)
        except ImportError:
            # fallback: 轮询 /history
            return self._poll_history(prompt_id, timeout, on_progress)
        except Exception:
            return self._poll_history(prompt_id, timeout, on_progress)

        start_time = time.time()
        try:
            while time.time() - start_time < timeout:
                try:
                    raw = ws.recv()
                except Exception:
                    break

                if isinstance(raw, bytes):
                    # 二进制消息（可能是预览图），跳过
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if msg_type == "execution_start":
                    progress.status = "running"
                    if on_progress:
                        on_progress(progress)

                elif msg_type == "execution_cached":
                    if "nodes" in data:
                        for n in data["nodes"]:
                            progress.executed_nodes.append(str(n))
                    if on_progress:
                        on_progress(progress)

                elif msg_type == "executing":
                    node = data.get("node")
                    if node is None:
                        # 执行完毕
                        progress.status = "done"
                        if on_progress:
                            on_progress(progress)
                        break
                    progress.current_node = str(node)
                    if on_progress:
                        on_progress(progress)

                elif msg_type == "progress":
                    value = data.get("value", 0)
                    max_val = data.get("max", 100)
                    progress.progress = value / max_val if max_val > 0 else 0
                    if on_progress:
                        on_progress(progress)

                elif msg_type == "executed":
                    node = data.get("node")
                    if node:
                        progress.executed_nodes.append(str(node))
                        # 提取输出图片
                        output = data.get("output", {})
                        for key, val in output.items():
                            if isinstance(val, list):
                                for item in val:
                                    if isinstance(item, dict) and "filename" in item:
                                        progress.output_images.append(
                                            f"{self.base_url}/view?filename={item['filename']}&type=output"
                                        )

                elif msg_type == "status":
                    pass  # 队列状态心跳

                if on_progress:
                    on_progress(progress)

        finally:
            ws.close()

        # 获取最终结果
        if progress.status == "done":
            history = self.get_history(prompt_id)
            if history and "outputs" in history:
                for node_id, node_out in history["outputs"].items():
                    for key, val in node_out.items():
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict) and "filename" in item:
                                    img_url = (
                                        f"{self.base_url}/view?"
                                        f"filename={item['filename']}"
                                        f"&type=output"
                                        f"&subfolder={item.get('subfolder', '')}"
                                    )
                                    if img_url not in progress.output_images:
                                        progress.output_images.append(img_url)

        progress.error = None if progress.status == "done" else "超时或失败"
        return progress

    def _poll_history(self, prompt_id: str, timeout: int,
                      on_progress: Optional[Callable] = None) -> ExecutionProgress:
        """降级方案：轮询 /history 替代 WebSocket"""
        progress = ExecutionProgress(prompt_id=prompt_id)
        start = time.time()

        while time.time() - start < timeout:
            history = self.get_history(prompt_id)
            if history:
                progress.status = "done"
                if "outputs" in history:
                    for node_id, node_out in history["outputs"].items():
                        for key, val in node_out.items():
                            if isinstance(val, list):
                                for item in val:
                                    if isinstance(item, dict) and "filename" in item:
                                        progress.output_images.append(
                                            f"{self.base_url}/view?filename={item['filename']}&type=output"
                                        )
                progress.error = None
                if on_progress:
                    on_progress(progress)
                return progress

            progress.status = "running"
            progress.progress = min(0.95, (time.time() - start) / timeout)
            if on_progress:
                on_progress(progress)

            time.sleep(2)

        progress.status = "error"
        progress.error = f"轮询超时 ({timeout}s)"
        return progress

    # =========================================================================
    # 便捷方法
    # =========================================================================

    def download_image(self, image_url: str, save_path: str | Path) -> Path:
        """下载生成结果图片到本地"""
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(image_url, str(save_path))
        return save_path

    def health_check(self) -> bool:
        """检查 ComfyUI 是否存活"""
        try:
            req = urllib.request.Request(f"{self.base_url}/")
            resp = urllib.request.urlopen(req, timeout=3)
            return resp.status == 200
        except Exception:
            return False

    def get_queue_info(self) -> Dict:
        """获取队列信息"""
        try:
            req = urllib.request.Request(f"{self.base_url}/queue")
            resp = urllib.request.urlopen(req, timeout=5)
            return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {}
