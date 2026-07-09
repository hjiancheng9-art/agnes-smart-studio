"""ComfyFlow Compiler — 安全门

提交 workflow 到 ComfyUI 前的安全检查。
"""

from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class SafetyIssue:
    code: str
    message: str
    severity: str = "error"   # error / warning


@dataclass
class SafetyReport:
    passed: bool = False
    issues: List[SafetyIssue] = field(default_factory=list)


# =============================================================================
# Workflow 安全门
# =============================================================================

# 已知的安全 class_type 白名单
SAFE_CLASS_TYPES: Set[str] = {
    # 模型加载
    "CheckpointLoaderSimple", "UNETLoader", "UnetLoaderGGUF",
    "CLIPLoader", "DualCLIPLoader", "VAELoader",
    "LoraLoader", "LoraLoaderModelOnly",
    # 条件
    "CLIPTextEncode", "CLIPSetLastLayer",
    # 潜变量
    "EmptyLatentImage", "EmptySD3LatentImage", "EmptyFlux2LatentImage",
    "EmptyLTXVLatentVideo", "VAEEncode", "VAEDecode", "VAEDecodeTiled",
    # 采样
    "KSampler", "KSamplerAdvanced", "KSamplerSelect",
    "SamplerCustomAdvanced", "RandomNoise", "ManualSigmas",
    "CFGGuider", "BasicGuider",
    # 图像
    "LoadImage", "SaveImage", "PreviewImage", "ImageScaleBy",
    "ImageScaleToTotalPixels", "ImageResizeKJv2",
    # 视频
    "VHS_VideoCombine", "VHS_VideoInfo",
    "LTXVConditioning", "LTXVImgToVideoInplace", "LTXVPreprocess",
    "LTXVCropGuides", "LTXVAudioVAELoader", "LTXVAudioVAEDecode",
    "LTXVConcatAVLatent", "LTXVSeparateAVLatent",
    # ControlNet
    "ControlNetLoader", "ControlNetApply",
    # 放大
    "UpscaleModelLoader", "ImageUpscaleWithModel",
    # 工具
    "Note", "Reroute", "PrimitiveNode",
    # Flux 专用
    "DualCLIPLoader",
}

# 禁止的高风险 class_type 列表
BLOCKED_CLASS_TYPES: Set[str] = {
    "ExecutePython", "RunShell", "DownloadModel", "WriteFile",
}


class WorkflowSafetyGate:
    """工作流安全门 — 提交 /prompt 前检查"""

    def __init__(self, max_nodes: int = 200, max_vram_gb: float = 48.0):
        self.max_nodes = max_nodes
        self.max_vram_gb = max_vram_gb

    def inspect(self, workflow: Dict[str, Any],
                budget_vram_gb: float = 0.0) -> SafetyReport:
        """检查 workflow 是否存在安全风险"""
        issues = []

        if not workflow:
            issues.append(SafetyIssue("empty_workflow", "工作流为空"))
            return SafetyReport(passed=False, issues=issues)

        # 1. 节点数限制
        if len(workflow) > self.max_nodes:
            issues.append(SafetyIssue(
                "too_many_nodes",
                f"节点数 {len(workflow)} 超过限制 {self.max_nodes}",
                severity="warning",
            ))

        # 2. 逐个节点检查
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                issues.append(SafetyIssue(
                    "invalid_node", f"节点 [{node_id}] 不是合法对象"
                ))
                continue

            ct = node.get("class_type", "")

            # 禁止的节点
            if ct in BLOCKED_CLASS_TYPES:
                issues.append(SafetyIssue(
                    "blocked_class_type",
                    f"节点 [{node_id}] 类型 '{ct}' 被禁止",
                ))

            # 未知节点（警告）
            if ct and ct not in SAFE_CLASS_TYPES and "custom" not in ct.lower():
                issues.append(SafetyIssue(
                    "unknown_class_type",
                    f"节点 [{node_id}] 类型 '{ct}' 不在内置白名单中",
                    severity="warning",
                ))

        # 3. 显存预算
        if budget_vram_gb > 0:
            estimated_vram = self._estimate_vram(workflow)
            if estimated_vram > budget_vram_gb:
                issues.append(SafetyIssue(
                    "vram_overflow",
                    f"估算显存 {estimated_vram}GB > 预算 {budget_vram_gb}GB",
                    severity="warning",
                ))

        return SafetyReport(
            passed=len([i for i in issues if i.severity == "error"]) == 0,
            issues=issues,
        )

    def _estimate_vram(self, workflow: Dict[str, Any]) -> float:
        """粗略估算 workflow 显存需求"""
        vram_map = {
            "UNETLoader": 4.0, "UnetLoaderGGUF": 2.0,
            "CheckpointLoaderSimple": 2.0,
            "VAELoader": 0.5, "CLIPLoader": 0.5,
            "SamplerCustomAdvanced": 0.5, "KSampler": 0.5,
        }
        total = 0.0
        base_loaded = False
        for node in workflow.values():
            ct = node.get("class_type", "")
            if ct in vram_map:
                total += vram_map[ct]
            if ct in ("UNETLoader", "CheckpointLoaderSimple"):
                if base_loaded:
                    total += 0  # 已经算过
                base_loaded = True
        return max(total, 2.0)


# =============================================================================
# 子进程安全
# =============================================================================

@dataclass
class CommandResult:
    ok: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1


ALLOWED_COMMANDS: Set[str] = {
    "nvidia-smi", "nvidia-smi.exe",
}


def run_safe_command(args: List[str], timeout: int = 10) -> CommandResult:
    """安全执行子进程（白名单控制）"""
    if not args:
        return CommandResult(ok=False, stderr="empty command")

    exe = Path(args[0]).name
    if exe not in ALLOWED_COMMANDS:
        return CommandResult(ok=False, stderr=f"command not allowed: {exe}")

    try:
        completed = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
        return CommandResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(ok=False, stderr="timeout")
    except Exception as e:
        return CommandResult(ok=False, stderr=str(e))


# =============================================================================
# 路径安全
# =============================================================================

def safe_resolve_path(path: str, allowed_roots: List[str]) -> Optional[Path]:
    """安全解析路径，确保不逃逸出允许的根目录"""
    try:
        target = Path(path).resolve()
        for root in allowed_roots:
            root_path = Path(root).resolve()
            if root_path in target.parents or target == root_path:
                return target
        return None
    except Exception:
        return None
