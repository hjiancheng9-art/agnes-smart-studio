"""ComfyFlow Compiler — ComfyUI 环境扫描器"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Optional
import json
import re

from .models import EnvironmentProfile


# 标准模型子目录
MODEL_SUBDIRS = {
    "checkpoints": ["checkpoints", "models/checkpoints"],
    "loras": ["loras", "models/loras"],
    "vaes": ["vae", "vaes", "models/vae"],
    "controlnet": ["controlnet", "control_net", "models/controlnet"],
    "upscale": ["upscale_models", "models/upscale_models"],
    "video": ["video", "models/video"],
    "unet": ["unet", "models/unet"],
    "clip": ["clip", "models/clip"],
}


def scan_comfyui_environment(comfyui_path: str | Path) -> EnvironmentProfile:
    """
    离线扫描 ComfyUI 环境：
    - custom_nodes 目录 → 已安装节点列表
    - models 目录 → 各类型模型文件
    - 自动识别 SDXL / SD1.5 / Flux
    """
    comfyui_path = Path(comfyui_path)
    env = EnvironmentProfile(comfyui_path=str(comfyui_path.resolve()))

    if not comfyui_path.exists():
        env.warnings.append(f"ComfyUI 路径不存在: {comfyui_path}")
        return env

    # 扫描 custom_nodes
    custom_nodes_dir = comfyui_path / "custom_nodes"
    if custom_nodes_dir.exists():
        for node_dir in custom_nodes_dir.iterdir():
            if node_dir.is_dir() and not node_dir.name.startswith("."):
                env.custom_nodes.append(node_dir.name)
                # 检查 __init__.py 获取包名
                init_py = node_dir / "__init__.py"
                if init_py.exists():
                    content = init_py.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r'NODE_CLASS_MAPPINGS\s*=', content)
                    if m:
                        env.custom_node_packages.append({
                            "dir": node_dir.name,
                            "has_mappings": True,
                        })

    # 扫描 models 目录
    models_dir = comfyui_path / "models"
    if not models_dir.exists():
        env.warnings.append(f"models 目录不存在: {models_dir}")
        return env

    # 扫描各子目录
    for model_type, subdirs in MODEL_SUBDIRS.items():
        files = []
        for sub in subdirs:
            d = models_dir / sub
            if d.exists():
                files.extend(_scan_model_files(d))
        
        model_list = sorted(set(files))
        setattr(env, model_type, model_list)

    # 自动识别基础模型
    for ckpt in env.checkpoints:
        name_lower = ckpt.lower()
        if any(k in name_lower for k in ["xl", "sdxl", "sd_xl"]):
            env.has_sdxl = True
        if any(k in name_lower for k in ["sd1.5", "sd15", "v1-5", "1.5"]):
            env.has_sd15 = True
        if "flux" in name_lower:
            env.has_flux = True
        if "ltx" in name_lower or "ltx-video" in name_lower:
            env.has_ltx = True

    # 也检查 clip 和 unet 目录
    for clip in env.clip_models:
        if "flux" in clip.lower():
            env.has_flux = True
    for unet in env.unet_models:
        if "flux" in unet.lower():
            env.has_flux = True
        if "ltx" in unet.lower():
            env.has_ltx = True

    # 检查 video 模型 (Wan / LTX)
    for vid in env.video_models:
        name_lower = vid.lower()
        if "wan" in name_lower:
            env.has_wan = True
        if "ltx" in name_lower:
            env.has_ltx = True

    # 读取 ComfyUI 版本
    try:
        main_py = comfyui_path / "main.py"
        if main_py.exists():
            content = main_py.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)', content)
            if m:
                env.comfyui_version = m.group(1)
    except Exception:
        pass

    # 检查 extra_model_paths.yaml
    extra = comfyui_path / "extra_model_paths.yaml"
    if extra.exists():
        env.warnings.append("发现 extra_model_paths.yaml，可能包含额外模型路径")
        # 简单解析 YAML 行
        for line in extra.read_text(encoding="utf-8", errors="ignore").split("\n"):
            if ":" in line and "\\" in line:
                path_part = line.split(":")[1].strip().strip('"').strip("'")
                p = Path(path_part)
                if p.exists():
                    for model_type, subdirs in MODEL_SUBDIRS.items():
                        for sub in subdirs:
                            d = p / sub
                            if d.exists():
                                files = _scan_model_files(d)
                                existing = getattr(env, model_type, [])
                                setattr(env, model_type, list(set(existing + files)))

    return env


def _scan_model_files(directory: Path) -> List[str]:
    """扫描目录下的模型文件，返回相对路径列表"""
    extensions = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
    files = []
    try:
        for f in directory.iterdir():
            if f.is_file() and f.suffix.lower() in extensions:
                files.append(f.name)
            elif f.is_dir():
                # 扫描一层子目录
                for sub in f.iterdir():
                    if sub.is_file() and sub.suffix.lower() in extensions:
                        files.append(f"{f.name}/{sub.name}")
    except PermissionError:
        pass
    return files


def detect_comfyui_paths() -> List[Path]:
    """自动检测系统中可能的 ComfyUI 安装路径"""
    candidates = []

    # Windows 常见位置
    if Path("C:/Program Files/ComfyUI").exists():
        candidates.append(Path("C:/Program Files/ComfyUI"))
    user_dir = Path.home()
    for p in [
        user_dir / "ComfyUI",
        user_dir / "Documents/ComfyUI",
        user_dir / "Downloads/ComfyUI",
        Path("D:/ComfyUI"),
        Path("E:/ComfyUI"),
    ]:
        if p.exists():
            candidates.append(p)

    # 检查当前目录
    for p in [Path("./ComfyUI"), Path("../ComfyUI")]:
        if p.exists():
            candidates.append(p.resolve())

    return candidates
