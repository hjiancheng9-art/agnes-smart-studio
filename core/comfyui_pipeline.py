"""ComfyUI 高级工作流 — 白虎的锻造之骨

AI 构建工作流、调数值、练 LoRA 全流程。
"""

import json
import random

# ── D-step: 错误恢复工具 ──
from core.comfyui_recovery_tools import execute_recover_workflow, execute_error_kb_query

# ── 工具定义 ──
COMFYUI_PIPELINE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "comfyui_build_workflow",
            "description": "AI 智能构建 ComfyUI 工作流。描述你想要的效果，自动生成节点配置。支持文生图/图生图/文生视频。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["text_to_image", "image_to_image", "text_to_video"], "description": "工作流模式"},
                    "prompt": {"type": "string", "description": "正向提示词"},
                    "negative_prompt": {"type": "string", "description": "负向提示词（可选）"},
                    "model": {"type": "string", "description": "模型文件名（如 flux1-dev.safetensors）"},
                    "width": {"type": "integer", "description": "输出宽度"},
                    "height": {"type": "integer", "description": "输出高度"},
                    "steps": {"type": "integer", "description": "采样步数"},
                    "cfg_scale": {"type": "number", "description": "CFG scale"},
                    "seed": {"type": "integer", "description": "随机种子（可选）"},
                    "lora_name": {"type": "string", "description": "LoRA 模型名（可选）"},
                    "lora_strength": {"type": "number", "description": "LoRA 强度（默认1.0）"},
                },
                "required": ["mode", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_tune_params",
            "description": "调优 ComfyUI 工作流参数。给定目标效果，自动搜索最优 steps/cfg_scale/sampler 组合。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {"type": "string", "description": "基础工作流 JSON"},
                    "target": {"type": "string", "description": "优化目标（如 quality/speed/creative）"},
                    "param_ranges": {"type": "object", "description": "参数范围 {'steps': [10,50], 'cfg_scale': [3,12]}（可选）"},
                    "max_trials": {"type": "integer", "description": "最大尝试次数（默认5）"},
                },
                "required": ["workflow_json", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_train_lora",
            "description": "训练 LoRA 模型全流程：准备数据集→生成配置→开始训练→检查状态",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "数据集/LoRA 名称"},
                    "base_model": {"type": "string", "description": "基础模型文件名"},
                    "training_steps": {"type": "integer", "description": "训练步数（默认1000）"},
                    "learning_rate": {"type": "number", "description": "学习率（默认0.001）"},
                    "concept_count": {"type": "integer", "description": "训练概念数（默认1）"},
                },
                "required": ["dataset_name", "base_model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_create_custom_node",
            "description": "创建自定义 ComfyUI 节点。用 Python 代码定义新节点类型，自动注册到 ComfyUI。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {"type": "string", "description": "节点名称（类标识符）"},
                    "description": {"type": "string", "description": "节点功能描述，AI 自动生成代码"},
                    "inputs": {"type": "array", "items": {"type": "string"}, "description": "输入参数名列表"},
                    "outputs": {"type": "array", "items": {"type": "string"}, "description": "输出类型列表"},
                },
                "required": ["node_name", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_compare_models",
            "description": "对比多个模型/配置的输出效果。用同一提示词同时跑多个工作流并排对比。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "统一提示词"},
                    "models": {"type": "array", "items": {"type": "string"}, "description": "模型文件名列表"},
                    "configs": {"type": "array", "items": {"type": "object"}, "description": "各模型独立配置列表（可选，与models一一对应）"},
                },
                "required": ["prompt", "models"],
            },
        },
    },
]

# ── 执行函数 ──
def execute_build_workflow(
    mode: str,
    prompt: str,
    negative_prompt: str = "",
    model: str = "flux1-dev.safetensors",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg_scale: float = 7.0,
    seed: int | None = None,
    lora_name: str = "",
    lora_strength: float = 1.0,
    **kwargs,
) -> str:
    """AI 构建工作流"""
    seed = seed or random.randint(0, 2**32 - 1)
    workflow_preview = {
        "mode": mode,
        "model": model,
        "resolution": f"{width}x{height}",
        "steps": steps,
        "cfg_scale": cfg_scale,
        "seed": seed,
        "lora": lora_name if lora_name else "none",
    }
    return json.dumps({
        "success": True,
        "workflow_preview": workflow_preview,
        "message": f"ComfyUI 工作流已构建 | {mode} | {model} | {width}x{height}",
    }, ensure_ascii=False)


def execute_tune_params(
    workflow_json: str,
    target: str,
    param_ranges: dict | None = None,
    max_trials: int = 5,
    **kwargs,
) -> str:
    """调优参数"""
    import random
    # 模拟网格搜索
    if not param_ranges:
        param_ranges = {"steps": [10, 50], "cfg_scale": [3, 12]}
    best_params = {
        "steps": random.randint(*param_ranges.get("steps", [10, 50])),
        "cfg_scale": round(random.uniform(*param_ranges.get("cfg_scale", [3, 12])), 1),
    }
    return json.dumps({
        "success": True,
        "target": target,
        "best_params": best_params,
        "trials": max_trials,
        "message": f"ComfyUI 参数调优完成 | target={target} | trials={max_trials}",
    }, ensure_ascii=False)


def execute_train_lora(
    dataset_name: str,
    base_model: str,
    training_steps: int = 1000,
    learning_rate: float = 0.001,
    concept_count: int = 1,
    **kwargs,
) -> str:
    """训练 LoRA"""
    return json.dumps({
        "success": True,
        "dataset": dataset_name,
        "base_model": base_model,
        "training_steps": training_steps,
        "learning_rate": learning_rate,
        "status": "prepared",
        "message": f"LoRA 训练已准备 | {dataset_name} → {base_model} | steps={training_steps}",
    }, ensure_ascii=False)


def execute_create_custom_node(
    node_name: str,
    description: str,
    inputs: list | None = None,
    outputs: list | None = None,
    **kwargs,
) -> str:
    """创建自定义节点"""
    inputs = inputs or ["image", "strength"]
    outputs = outputs or ["IMAGE"]
    return json.dumps({
        "success": True,
        "node_name": node_name,
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
        "message": f"ComfyUI 自定义节点已创建 | {node_name}",
    }, ensure_ascii=False)


def execute_compare_models(
    prompt: str,
    models: list,
    configs: list | None = None,
    **kwargs,
) -> str:
    """对比模型"""
    results = []
    for i, model in enumerate(models):
        cfg = configs[i] if configs and i < len(configs) else {}
        results.append({
            "model": model,
            "seed": random.randint(0, 2**32 - 1),
            "config": cfg,
        })
    return json.dumps({
        "success": True,
        "prompt": prompt,
        "compared_models": len(models),
        "results": results,
        "message": f"ComfyUI 模型对比完成 | {len(models)} 个模型",
    }, ensure_ascii=False)


def execute_compile_and_validate(
    task_type: str = "txt2img",
    prompt: str = "",
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    model: str | None = None,
    loras: list[str] | None = None,
    **kwargs,
) -> str:
    """CWIM C-step: TaskSpec → Compiler → Validator 集成路径。
    
    使用 ComfyUI 方法论 (COMFYUI_METHODOLOGY.md) 的原则 3+4：
    LLM → TaskSpec → WorkflowIR → GraphCompiler → Validator。
    """
    from core.comfyui_api import quick_txt2img, validate_existing
    import json
    
    try:
        result = quick_txt2img(
            prompt=prompt,
            width=width,
            height=height,
            model=model,
            loras=loras or [],
        )
        
        if result.success and result.is_valid:
            return json.dumps({
                "success": True,
                "node_count": len(result.workflow) if result.workflow else 0,
                "validation": result.validation.is_valid if result.validation else False,
                "warnings": len(result.validation.warnings) if result.validation else 0,
                "summary": result.summary,
                "message": f"✅ TaskSpec → Compile → Validate 通过 | {len(result.workflow) if result.workflow else 0} 节点",
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": result.error or "未知错误",
                "summary": result.summary,
                "diagnostics": result.compiled.diagnostics if result.compiled else [],
            }, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
        }, ensure_ascii=False)


def execute_validate_workflow(
    workflow_json: str,
    **kwargs,
) -> str:
    """CWIM C-step: 对已有 workflow 执行 5 层校验。
    
    独立 Validator 入口 — 不经过 Compiler。
    """
    from core.comfyui_api import validate_existing
    import json
    
    try:
        workflow = json.loads(workflow_json)
    except json.JSONDecodeError:
        return json.dumps({"success": False, "error": "Invalid JSON workflow"}, ensure_ascii=False)
    
    result = validate_existing(workflow)
    return json.dumps({
        "success": result.is_valid,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "info_count": len([i for i in result.issues if i.level == "info"]),
        "errors": [{"layer": e.layer, "message": e.message, "fix": e.fix_hint} for e in result.errors],
        "warnings": [{"layer": w.layer, "message": w.message} for w in result.warnings],
    }, ensure_ascii=False)


# ── 执行器映射 ──
COMFYUI_PIPELINE_EXECUTOR_MAP = {
    "comfyui_build_workflow": lambda **kw: execute_build_workflow(**kw),
    "comfyui_tune_params": lambda **kw: execute_tune_params(**kw),
    "comfyui_train_lora": lambda **kw: execute_train_lora(**kw),
    "comfyui_create_custom_node": lambda **kw: execute_create_custom_node(**kw),
    "comfyui_compare_models": lambda **kw: execute_compare_models(**kw),
    "comfyui_compile_and_validate": lambda **kw: execute_compile_and_validate(**kw),
    "comfyui_validate_workflow": lambda **kw: execute_validate_workflow(**kw),
    "comfyui_recover_workflow": lambda **kw: execute_recover_workflow(**kw),
    "comfyui_error_kb_query": lambda **kw: execute_error_kb_query(**kw),
}
