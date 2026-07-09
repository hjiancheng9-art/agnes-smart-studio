"""OutputContract — 输出产物收集契约

从 ComfyUI /history 响应中提取产物路径和类型。
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path

from .errors import OutputNotFoundError


@dataclass
class OutputFile:
    """单个输出文件"""
    filename: str
    folder: str
    type: str  # image, video, audio
    full_path: str = ""
    size_bytes: int = 0
    thumbnail: str = ""

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.full_path) if self.full_path else False


@dataclass
class OutputResult:
    """输出收集结果"""
    success: bool = False
    files: list[OutputFile] = field(default_factory=list)
    output_dir: str = ""
    prompt_id: str = ""
    count: int = 0

    @property
    def images(self) -> list[OutputFile]:
        return [f for f in self.files if f.type == "image"]

    @property
    def videos(self) -> list[OutputFile]:
        return [f for f in self.files if f.type == "video"]

    @property
    def summary(self) -> str:
        parts = []
        if self.images:
            parts.append(f"{len(self.images)} images")
        if self.videos:
            parts.append(f"{len(self.videos)} videos")
        return f"Output: {', '.join(parts) if parts else 'none'}"


DEFAULT_OUTPUT_DIRS = [
    "C:/ComfyUI/output",
    "../ComfyUI/output",
    "./ComfyUI/output",
]


class OutputCollector:
    """输出收集器 — 从 history 结果定位产物文件"""

    def __init__(self, comfyui_output_dir: str | None = None):
        self.comfyui_output_dir = comfyui_output_dir or self._find_output_dir()

    def collect(self, prompt_id: str, history_data: dict, output_dir: str = "") -> OutputResult:
        """收集执行产物

        Args:
            prompt_id: 执行的 prompt_id
            history_data: /history 返回的数据
            output_dir: 复制到指定目录（可选）

        Returns:
            OutputResult
        """
        entry = history_data.get(prompt_id, history_data)
        outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}

        files = []
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            for key, value in node_output.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            of = self._parse_output_item(item)
                            if of:
                                files.append(of)
                elif isinstance(value, dict):
                    of = self._parse_output_item(value)
                    if of:
                        files.append(of)

        # 去重
        seen = set()
        unique_files = []
        for f in files:
            if f.filename not in seen:
                seen.add(f.filename)
                unique_files.append(f)

        # 可选：复制到 output_dir
        if output_dir and unique_files:
            os.makedirs(output_dir, exist_ok=True)
            import shutil
            for f in unique_files:
                if f.exists:
                    dst = os.path.join(output_dir, f.filename)
                    shutil.copy2(f.full_path, dst)
                    f.full_path = dst

        return OutputResult(
            success=len(unique_files) > 0,
            files=unique_files,
            output_dir=output_dir or self.comfyui_output_dir or "",
            prompt_id=prompt_id,
            count=len(unique_files),
        )

    def _parse_output_item(self, item: dict) -> Optional[OutputFile]:
        """解析单个输出条目"""
        filename = item.get("filename", "")
        folder = item.get("folder", item.get("subfolder", ""))
        if not filename:
            return None

        # 判断类型
        ext = Path(filename).suffix.lower()
        ftype = "image"
        if ext in (".mp4", ".webm", ".mov", ".avi", ".gif"):
            ftype = "video"
        elif ext in (".wav", ".mp3", ".flac", ".aac"):
            ftype = "audio"

        # 找完整路径
        base = self.comfyui_output_dir
        full_path = ""
        if base and folder:
            full_path = os.path.join(base, folder, filename)
        elif base:
            full_path = os.path.join(base, filename)
        elif folder:
            full_path = os.path.join(folder, filename)

        size = 0
        if full_path and os.path.isfile(full_path):
            size = os.path.getsize(full_path)

        return OutputFile(
            filename=filename,
            folder=folder,
            type=ftype,
            full_path=full_path,
            size_bytes=size,
        )

    def _find_output_dir(self) -> str:
        """自动查找 ComfyUI output 目录"""
        for d in DEFAULT_OUTPUT_DIRS:
            if os.path.isdir(d):
                return os.path.abspath(d)
        return ""
