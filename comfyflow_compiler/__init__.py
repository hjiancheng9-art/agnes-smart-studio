"""ComfyFlow Compiler — 零门槛 ComfyUI 高级工作流生成器"""

__version__ = "6.5.0"
__version_name__ = "Polish Closure"

from .compiler import ComfyFlowCompiler
from .models import CompileResult, TaskSpec
from .intent_parser import parse_intent
from .launcher import ComfyUILauncher, ComfyUIStatus, launch_comfyui
from .api_client import ComfyAPIClient, ExecutionProgress
from .workflow_parser import (
    convert_to_api, convert_to_save_v1, detect_format,
    WorkflowFormat, parse_workflow_file,
)
from .user_facing import (
    UserFacingResult, UserMessage, build_user_result, translate_error,
)
from .safety_gate import (
    WorkflowSafetyGate, SafetyReport, SafetyIssue,
    run_safe_command, safe_resolve_path,
)
from .parameter_table import PARAMETERS, get_param, get_param_def, resolve_resolution
from .blueprint_miner import BlueprintMiner, ProductionBlueprint
from .blueprint_packer import BlueprintPacker
from .blueprint_loader import auto_mine_blueprints
from .workflow_enricher import WorkflowEnricher, WorkflowAnalyzer

__all__ = [
    "ComfyFlowCompiler", "CompileResult", "TaskSpec",
    "ComfyUILauncher", "ComfyUIStatus", "launch_comfyui",
    "ComfyAPIClient", "ExecutionProgress",
    "convert_to_api", "convert_to_save_v1", "detect_format",
    "WorkflowFormat", "parse_workflow_file",
    "UserFacingResult", "UserMessage", "build_user_result", "translate_error",
    "WorkflowSafetyGate", "SafetyReport", "SafetyIssue",
    "run_safe_command", "safe_resolve_path",
    "PARAMETERS", "get_param", "get_param_def", "resolve_resolution",
    "BlueprintMiner", "ProductionBlueprint", "BlueprintPacker", "auto_mine_blueprints",
    "WorkflowEnricher", "WorkflowAnalyzer",
]

