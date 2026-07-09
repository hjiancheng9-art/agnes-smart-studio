"""Capability — ComfyUI 运行时能力探测

探测真实 ComfyUI 环境：可用节点、模型、硬件配置。
"""

from .snapshot import CapabilitySnapshot, probe_comfyui
from .comfy_probe import ComfyProbe, ComfyProbeError
from .model_index import ModelIndex
from .node_index import NodeIndex
from .compatibility import BlueprintCompatibilityMatcher, CompatibilityScore, NODE_FALLBACKS, MODEL_FALLBACKS
from .errors import CapabilityError, ComfyOfflineError, MissingNodeError, MissingModelError

__all__ = [
    "CapabilitySnapshot", "probe_comfyui",
    "ComfyProbe", "ComfyProbeError",
    "ModelIndex", "NodeIndex",
    "CapabilityError", "ComfyOfflineError", "MissingNodeError", "MissingModelError",
]
