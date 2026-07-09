# core/intelligence/policy.py
"""ExecutionPolicy — defines which P1-P7 modules are enabled for a task."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RunMode(str, Enum):
    FAST = "fast"          # Simple Q&A, no tools
    BALANCED = "balanced"  # Default chat mode
    DEEP = "deep"          # Complex engineering / architecture
    SAFE = "safe"          # High-risk file ops / shell
    DEBUG = "debug"        # Replay / diagnosis / failure reproduction


@dataclass(frozen=True)
class ExecutionPolicy:
    """Complete policy defining which intelligence modules are active."""
    mode: RunMode = RunMode.BALANCED

    # P1: Tool Validation
    enable_tool_validation: bool = True
    enable_self_correction: bool = True
    max_self_correction_attempts: int = 2

    # P2: Result Verification
    enable_result_verification: bool = True
    enable_diff_guard: bool = False

    # P3: Context Management
    enable_context_compiler: bool = True
    enable_context_compression: bool = False

    # P4: Multi-Agent
    enable_reviewer: bool = False
    enable_debate: bool = False
    enable_task_decomposer: bool = False

    # P5: Skill / Prompt Compiler
    enable_skill_compiler: bool = True
    enable_prompt_compiler: bool = True

    # P6: Telemetry
    trace_level: str = "normal"  # off / normal / verbose
    eval_recording: bool = True

    # Limits
    max_agent_rounds: int = 1
    reviewer_min_response_chars: int = 500

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "enable_tool_validation": self.enable_tool_validation,
            "enable_self_correction": self.enable_self_correction,
            "enable_result_verification": self.enable_result_verification,
            "enable_diff_guard": self.enable_diff_guard,
            "enable_context_compiler": self.enable_context_compiler,
            "enable_context_compression": self.enable_context_compression,
            "enable_reviewer": self.enable_reviewer,
            "enable_debate": self.enable_debate,
            "enable_task_decomposer": self.enable_task_decomposer,
            "enable_skill_compiler": self.enable_skill_compiler,
            "enable_prompt_compiler": self.enable_prompt_compiler,
            "trace_level": self.trace_level,
            "max_agent_rounds": self.max_agent_rounds,
        }

    def summary(self) -> str:
        """Human-readable policy summary."""
        enabled = []
        disabled = []
        for key, val in self.to_dict().items():
            if key == "mode":
                continue
            if val is True:
                enabled.append(key.replace("enable_", ""))
            elif val is False:
                disabled.append(key.replace("enable_", ""))
        return (
            f"⚡ {self.mode.value.upper()} mode\n"
            f"   ✅ {', '.join(enabled[:10])}\n"
            f"   ❌ {', '.join(disabled[:10])}"
        )
