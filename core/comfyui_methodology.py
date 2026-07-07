"""ComfyUI 方法论引擎 — 加载并注入 COMFYUI_METHODOLOGY.md

将 CWIM（ComfyUI Workflow Intelligence Methodology）注入系统提示，
使智能体在 ComfyUI 任务中遵循一致的决策流程。

使用方法：
    from core.comfyui_methodology import get_comfyui_methodology
    methodology_text = get_comfyui_methodology()

集成：
    chat_prompt.py 中的 build_system_prompt() 在 comfyui_enabled=True 时
    自动调用此模块追加方法论内容。
"""

import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

METHODOLOGY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "COMFYUI_METHODOLOGY.md")


@lru_cache(maxsize=1)
def get_comfyui_methodology() -> str:
    """加载并缓存 COMFYUI_METHODOLOGY.md 的完整内容。"""
    if not os.path.exists(METHODOLOGY_FILE):
        logger.warning("COMFYUI_METHODOLOGY.md 不存在于 %s", METHODOLOGY_FILE)
        return ""
    try:
        with open(METHODOLOGY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info("已加载 ComfyUI 方法论 (%d 字符)", len(content))
        return content
    except Exception as e:
        logger.error("加载 COMFYUI_METHODOLOGY.md 失败: %s", e)
        return ""


def format_methodology_prompt() -> str:
    """生成用于注入系统提示的方法论摘要。"""
    full = get_comfyui_methodology()
    if not full:
        return ""

    # 提取核心原则和决策树
    return f"""
# ComfyUI Agent Methodology (CWIM) — 方法论文档已加载

以下原则是 ComfyUI 工作流智能体的硬性执行准则：

## 10 条核心原则
1. 永远不要先生成 Workflow — 先理解任务类型/输入输出/约束
2. 优先复用成熟 Workflow — 模板 > Motif组合 > 子图 > 最后才生成
3. LLM 不直接生成 ComfyUI JSON — 必须经过 TaskSpec → WorkflowIR → GraphCompiler
4. 所有 Workflow 必须经过 Validator 校验
5. 失败不是结束，而是学习 — 保存错误/参数/patch
6. 参数不是数字，而是语义 — 按语义维度推荐
7. 所有推荐必须可解释 — 告诉用户"为什么推荐这个"
8. LoRA 是项目，不是文件 — 全生命周期管理
9. Workflow 是图，不是 JSON — 基于图结构操作
10. 用户面对任务，不是节点 — 术语面向任务

## 主决策流程
收到需求 → 类型判断 → 输入分析 → 约束检查 → 匹配决策（精确匹配→Motif组合→编译生成）→ 执行 → 成功/失败处理

完整方法论参考: COMFYUI_METHODOLOGY.md
"""


def inject_comfyui_methodology(system_prompt: str) -> str:
    """将 ComfyUI 方法论注入到已有的系统提示中。"""
    methodology_part = format_methodology_prompt()
    if not methodology_part:
        return system_prompt

    # 追加到系统提示末尾
    return system_prompt.rstrip() + "\n\n" + methodology_part
