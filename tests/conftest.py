"""
ComfyFlow Compiler — 测试用共享 fixture 和 mock 数据
"""
from __future__ import annotations
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# =============================================================================
# 样本工作流（API Prompt Format）
# =============================================================================

SAMPLE_SDXL_WORKFLOW = {
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cinematic cat", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "nsfw, low quality", "clip": ["4", 1]}},
    "8": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "9": {"class_type": "KSampler", "inputs": {
        "model": ["4", 0], "positive": ["6", "conditioning"],
        "negative": ["7", "conditioning"], "latent_image": ["8", "latent"],
        "seed": 0, "steps": 25, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0
    }},
    "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", "latent"], "vae": ["4", "vae"]}},
    "11": {"class_type": "SaveImage", "inputs": {"images": ["10", "image"], "filename_prefix": "test"}},
}

SAMPLE_LTX_WORKFLOW = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "ltx.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "ltxv"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "10": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["9", "image"], "frame_rate": 24, "loop_count": 0, "format": "video/h264-mp4"}},
}

SAMPLE_SAVE_V1 = {
    "version": 1,
    "config": {},
    "state": {},
    "nodes": [
        {"id": 4, "type": "CheckpointLoaderSimple", "pos": [100, 100], "size": [300, 200],
         "flags": {}, "order": 0, "mode": 0,
         "inputs": [], "outputs": [],
         "properties": {"Node name for S&R": "CheckpointLoaderSimple"},
         "widgets_values": ["model.safetensors"]},
        {"id": 6, "type": "CLIPTextEncode", "pos": [400, 100], "size": [300, 200],
         "flags": {}, "order": 1, "mode": 0,
         "inputs": [{"name": "clip", "type": "CLIP", "link": 1, "slot_index": 0}],
         "outputs": [],
         "properties": {"Node name for S&R": "CLIPTextEncode"},
         "widgets_values": ["a cat"]},
    ],
    "links": [
        {"id": 1, "origin_id": 4, "origin_slot": 1, "target_id": 6, "target_slot": 0, "type": "CLIP"},
    ],
    "groups": [],
    "reroutes": [],
    "extra": {},
    "models": [],
}

# =============================================================================
# Mock 环境数据
# =============================================================================

MOCK_ENV_WITH_SDXL = {
    "comfyui_path": "D:/ComfyUI_windows_portable/ComfyUI",
    "has_sdxl": True,
    "has_sd15": True,
    "has_flux": False,
    "has_ltx": False,
    "has_wan": False,
    "checkpoints": ["sd_xl_base_1.0.safetensors", "v1-5-pruned-emaonly.safetensors"],
    "custom_nodes": ["ComfyUI-Manager", "rgthree-comfy"],
}

MOCK_ENV_WITH_FLUX = {
    "comfyui_path": "D:/ComfyUI",
    "has_sdxl": True,
    "has_sd15": True,
    "has_flux": True,
    "has_ltx": False,
    "has_wan": False,
    "checkpoints": ["flux_dev_fp8.safetensors"],
    "custom_nodes": [],
}

MOCK_ENV_WITH_LTX = {
    "comfyui_path": "D:/ComfyUI",
    "has_sdxl": False,
    "has_sd15": False,
    "has_flux": False,
    "has_ltx": True,
    "has_wan": False,
    "checkpoints": ["ltx-2.3-22b-dev.safetensors"],
    "custom_nodes": ["ComfyUI-LTXVideo"],
}

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_sdxl_workflow():
    return dict(SAMPLE_SDXL_WORKFLOW)


@pytest.fixture
def sample_save_v1():
    return dict(SAMPLE_SAVE_V1)


@pytest.fixture
def mock_hardware_profile():
    from comfyflow_compiler.models import HardwareProfile
    return HardwareProfile(
        gpu_name="NVIDIA RTX 4060 Ti",
        vram_gb=16.0,
        cuda_available=True,
        source="test",
    )


@pytest.fixture
def mock_budget_high():
    from comfyflow_compiler.models import RuntimeBudget
    return RuntimeBudget(
        tier="high", vram_gb=16.0, score=8.5,
        supports_sdxl=True, supports_flux=True,
        max_resolution="1024x1536",
    )


@pytest.fixture
def mock_budget_low():
    from comfyflow_compiler.models import RuntimeBudget
    return RuntimeBudget(
        tier="low", vram_gb=4.0, score=1.0,
        supports_sdxl=False, supports_flux=False,
        supports_flux_gguf=True,
        max_resolution="512x512",
    )


@pytest.fixture
def compiler_with_sdxl():
    """集成测试用的半 mock Compiler"""
    from comfyflow_compiler.compiler import ComfyFlowCompiler
    comp = ComfyFlowCompiler()
    # Override with mock data
    from comfyflow_compiler.models import HardwareProfile, RuntimeBudget, EnvironmentProfile
    comp.hardware = HardwareProfile(gpu_name="RTX 4060 Ti", vram_gb=16.0, cuda_available=True, source="test")
    comp.budget = RuntimeBudget(tier="high", vram_gb=16.0, score=8.5, supports_sdxl=True, max_resolution="1024x1536")
    comp.env = EnvironmentProfile(
        comfyui_path="D:/ComfyUI",
        checkpoints=["sd_xl_base_1.0.safetensors"],
        has_sdxl=True, has_sd15=True,
    )
    return comp


# =============================================================================
# 辅助函数
# =============================================================================

def get_class_types(workflow: dict) -> set:
    return {n["class_type"] for n in workflow.values()}
