"""ComfyFlow Compiler — 面向小白的用户友好输出层

把 raw Workflow JSON 包装成小白看得懂的结果。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UserMessage:
    """一条面向用户的消息"""
    level: str = "info"                # info / success / warning / error
    title: str = ""
    message: str = ""
    suggestion: Optional[str] = None   # 建议操作


@dataclass
class UserFacingResult:
    """小白看到的编译结果"""
    success: bool = False
    title: str = ""                    # 一句话标题
    summary: str = ""                  # 2-3 句说明
    workflow_json: Optional[Dict[str, Any]] = None
    messages: List[UserMessage] = field(default_factory=list)
    technical_report: Optional[Dict[str, Any]] = None  # 给开发者


def build_user_result(
    success: bool,
    intent: str = "",
    quality_mode: str = "",
    blueprint_name: str = "",
    gpu_name: str = "",
    vram_gb: float = 0.0,
    workflow_json: Optional[Dict] = None,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    technical_report: Optional[Dict] = None,
) -> UserFacingResult:
    """从编译结果构建小白友好的输出"""

    msgs = []

    if success:
        intent_names = {
            "flux_generation": "Flux 高质量图像",
            "ltx_video": "LTX 视频",
            "wan_video": "Wan 视频",
            "character_replace": "换装",
            "face_swap": "换脸",
            "video_lipsync": "数字人对口型",
            "action_transfer": "动作迁移",
            "image_edit": "图像编辑",
        }
        intent_label = intent_names.get(intent, intent)

        return UserFacingResult(
            success=True,
            title=f"✅ {intent_label} 工作流已生成",
            summary=(
                f"已为你准备好 {intent_label} 方案，"
                f"使用了 {blueprint_name}，"
                f"质量模式：{quality_mode}。\n"
                f"当前硬件：{gpu_name}（{vram_gb}GB 显存），可以流畅运行。"
            ),
            workflow_json=workflow_json,
            messages=[
                UserMessage(
                    level="info",
                    title="使用方法",
                    message="把上面的 JSON 保存为 .json 文件，拖入 ComfyUI 窗口，点击「Queue Prompt」即开始生成。",
                    suggestion=None,
                ),
                UserMessage(
                    level="info",
                    title="小提示",
                    message="如果生成的图不满意，可以调整 prompt 重新生成。同样的需求也可以试试「高清」质量模式。",
                ),
            ],
            technical_report=technical_report,
        )

    # 失败场景
    error_messages = {
        "no_blueprint": "当前环境下没有找到可用的工作流方案。",
        "workflow_invalid": "生成的工作流结构有误，系统将自动重试。",
        "hardware_insufficient": "当前硬件配置低于最低要求。",
        "model_missing": "缺少必需的模型文件。",
    }

    error_text = "、".join(errors) if errors else "未知错误"
    matched = False
    for code, msg in error_messages.items():
        if code in error_text:
            msgs.append(UserMessage(level="error", title="出错了", message=msg, suggestion="试试降低质量要求，或切换到更简单的生成模式。"))
            matched = True
            break

    if not matched:
        msgs.append(UserMessage(
            level="error",
            title="生成失败",
            message=f"系统遇到了问题：{error_text[:100]}",
            suggestion="试试换个描述方式重新生成，或检查 ComfyUI 是否在运行。",
        ))

    if warnings:
        for w in warnings[:2]:
            msgs.append(UserMessage(level="warning", title="提示", message=w[:100]))

    return UserFacingResult(
        success=False,
        title="❌ 工作流生成失败",
        summary="很抱歉，当前条件下没能生成可运行的工作流。请参考下面的建议。",
        workflow_json=None,
        messages=msgs,
        technical_report=technical_report,
    )


# =============================================================================
# 错误翻译器
# =============================================================================

ERROR_TRANSLATIONS = {
    "missing_required_node": {
        "title": "缺少必要节点",
        "message": "当前环境缺少工作流所需的插件或节点。",
        "suggestion": "安装缺失的插件后重试，或使用基础版功能。",
    },
    "node_not_found": {
        "title": "节点未找到",
        "message": "工作流引用了不存在的节点。",
        "suggestion": "系统应自动修复，如果持续出现请联系开发者。",
    },
    "no_blueprint_available": {
        "title": "没有可用的方案",
        "message": "当前硬件和环境配置下，没有适合的工作流方案。",
        "suggestion": "试试降低质量要求，或安装更多模型和插件。",
    },
    "comfyui_not_running": {
        "title": "ComfyUI 未运行",
        "message": "没有检测到运行中的 ComfyUI。",
        "suggestion": "先启动 ComfyUI，再重新生成。",
    },
    "vram_insufficient": {
        "title": "显存不足",
        "message": "当前方案需要的显存超出你的硬件上限。",
        "suggestion": "系统已自动降级为低显存方案。",
    },
    "workflow_validation_error": {
        "title": "工作流格式不正确",
        "message": "生成的 workflow JSON 没有通过结构检查。",
        "suggestion": "系统应自动重试或切换备用蓝图。",
    },
    "default": {
        "title": "出了点问题",
        "message": "系统遇到了未知错误。",
        "suggestion": "换个描述试试，或检查 ComfyUI 是否正常运行。",
    },
}


def translate_error(error_code: str, detail: Optional[str] = None) -> dict:
    """把内部错误码翻译成小白能看懂的中文"""
    translation = ERROR_TRANSLATIONS.get(error_code, ERROR_TRANSLATIONS["default"])
    result = dict(translation)
    if detail:
        result["detail"] = detail
    return result
