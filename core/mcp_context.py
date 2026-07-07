"""
MCP 上下文感知注入器（v5.0→v6.0 升级）
=========================================
ChatGPT+智谱评审共识：MCP 全量注入导致上下文污染。
改为按任务类型动态注入，只加载当前任务相关的工具。

设计：
  - 工具按场景分组（code/creative/infra/web/comfyui/edge）
  - 根据 TaskSpec.intent_type 筛选工具列表
  - 轻量级检查 (ping) 而非全量连接
  - 注入到 TRM 时附带上文标签
"""

from __future__ import annotations

# MCP 工具 → 场景映射
MCP_TOOL_SCENES: dict[str, str] = {
    # Code 场景
    "run_test": "code", "run_lint": "code", "run_format": "code",
    "code_review": "code", "security_review": "code",
    "debug_inspect": "code", "tdd_run_tests": "code",
    "git_add_commit": "code", "git_branch": "code", "git_diff": "code",

    # Creative 场景
    "generate_image": "creative", "generate_video": "creative",
    "imagegen": "creative", "text_to_speech": "creative",
    "comfyui_submit_workflow": "creative",
    "comfyui_build_custom_workflow": "creative",

    # Infra 场景
    "run_bash": "infra", "run_python": "infra",
    "task_launch": "infra", "deploy_vercel": "infra",

    # Web 场景
    "web_search": "web", "web_fetch": "web",
    "github_search": "web", "github_repo_view": "web",
    "browser_screenshot": "web",

    # ComfyUI 专用
    "comfyui_status": "comfyui", "comfyui_list_models": "comfyui",
    "comfyui_get_node_info": "comfyui",
    "comfyui_lora_prepare": "comfyui",

    # Edge/CDP 专用
    "pw_navigate": "edge", "pw_screenshot": "edge",
}

# 意图类型 → 需要哪些场景的工具
INTENT_TO_SCENES = {
    "generate": ["creative", "comfyui"],
    "analyze": ["code", "infra"],
    "modify": ["code", "infra"],
    "search": ["web", "code"],
    "execute": ["infra", "code"],
    "review": ["code", "web"],
    "diagnose": ["code", "infra", "web"],
    "deploy": ["infra", "code"],
}


def filter_tools_by_intent(
    available_tools: list[str],
    intent_type: str,
) -> list[str]:
    """按意图类型筛选 MCP 工具列表"""
    needed_scenes = INTENT_TO_SCENES.get(intent_type, ["infra"])
    return [
        t for t in available_tools
        if MCP_TOOL_SCENES.get(t, "infra") in needed_scenes
    ]


def get_context_prompt(intent_type: str) -> str:
    """生成上下文感知的 MCP 可用工具提示（注入系统提示词用）"""
    scenes = INTENT_TO_SCENES.get(intent_type, ["infra"])
    return f"当前已加载 MCP 工具场景: {', '.join(scenes)}"
