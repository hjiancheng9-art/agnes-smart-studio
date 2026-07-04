"""ComfyUI 桥接工具 — 让 CRUX 通过 ComfyUI API 执行本地生图/生视频

CRUX 负责：理解意图、自由组合节点、编写提示词、自创节点
ComfyUI 负责：执行工作流、产出图像/视频

工具设计原则：
- 所有与 ComfyUI 的 HTTP 通信封装在此
- 不包含任何 LLM 调用或推理逻辑
- 纯执行层：查询节点、构建工作流、提交、轮询、校验
- 支持自由编排：不限于固定配方，可按需组合任意节点
"""

import json

# ── ComfyUI 配置 ──
# 优先从环境变量读取，否则使用默认本地地址
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "COMFYUI_BASE_URL",
    "COMFYUI_CUSTOM_NODES_DIR",
    "COMFYUI_EXECUTOR_MAP",
    "COMFYUI_POLL_INTERVAL",
    "COMFYUI_TIMEOUT",
    "COMFYUI_TOOLS",
    "LORA_OUTPUT_ROOT",
    "OUTPUT_ROOT",
    "execute_build_custom_workflow",
    "execute_clear_queue",
    "execute_create_custom_node",
    "execute_get_node_info",
    "execute_get_result",
    "execute_list_models",
    "execute_lora_check_status",
    "execute_lora_generate_config",
    "execute_lora_prepare_dataset",
    "execute_preview_workflow",
    "execute_status",
    "execute_submit_workflow",
]

COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
# SSRF 防护：自定义 ComfyUI URL 须为本地地址
from urllib.parse import urlparse as _urlparse

_cui_host = _urlparse(COMFYUI_BASE_URL).hostname or ""
_CUI_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}
if _cui_host and _cui_host not in _CUI_ALLOWED_HOSTS:
    import logging

    logging.getLogger("crux.comfyui").warning(
        "COMFYUI_BASE_URL=%s 不是本地地址，已重置为本地默认值。远程 ComfyUI 需手动允许。", COMFYUI_BASE_URL
    )
    COMFYUI_BASE_URL = "http://127.0.0.1:8188"
COMFYUI_TIMEOUT = int(os.environ.get("COMFYUI_TIMEOUT", "300"))  # 默认 5 分钟
COMFYUI_POLL_INTERVAL = 2  # 轮询间隔秒数
COMFYUI_CUSTOM_NODES_DIR = os.environ.get(
    "COMFYUI_CUSTOM_NODES_DIR",
    "",  # 默认从 object_info 推断，或手动设置
)

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# ============================================================
#  HTTP 工具函数
# ============================================================


def _comfyui_request(path: str, method: str = "GET", body: dict | None = None, timeout: int = 30) -> dict | bytes:
    """向 ComfyUI API 发送请求"""
    url = f"{COMFYUI_BASE_URL}{path}"
    data = None
    headers = {}

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        # timeout: 单值秒数（Windows Python 3.11 不支持 (connect, read) 元组）
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                return json.loads(content.decode("utf-8"))
            return content
    except urllib.error.URLError as e:
        return {"error": f"ComfyUI 连接失败: {e.reason}", "available": False}
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return {"error": str(e), "available": False}


# ============================================================
#  工具定义（OpenAI function calling 格式）
# ============================================================

COMFYUI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "comfyui_status",
            "description": "检查 ComfyUI 服务是否在线，获取基本状态信息（队列长度、已安装节点数）。生成工作流前先调用此工具确认服务可用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_list_models",
            "description": "列出 ComfyUI 中已安装的模型（大模型/LoRA/VAE/ControlNet/Upscale模型），用于判断可用资源。在工作流构建前调用以确认所需模型存在。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_submit_workflow",
            "description": "将工作流 JSON 提交到 ComfyUI 执行队列，并轮询等待结果。返回生成的图片文件路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {
                        "type": "string",
                        "description": "ComfyUI API 格式的工作流 JSON 字符串（不是画布格式）",
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "是否等待生成完成，默认 true。设为 false 时仅提交并返回 prompt_id。",
                        "default": True,
                    },
                },
                "required": ["workflow_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_result",
            "description": "根据 prompt_id 查询 ComfyUI 工作流的执行结果。用于异步提交后的结果查询。",
            "parameters": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string", "description": "提交工作流时返回的 prompt_id"}},
                "required": ["prompt_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_preview_workflow",
            "description": "将工作流 JSON 发送到 ComfyUI 画布进行可视化预览和手动调整。不提交执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {
                        "type": "string",
                        "description": "ComfyUI 画布格式的工作流 JSON（含节点位置等UI信息）",
                    }
                },
                "required": ["workflow_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_clear_queue",
            "description": "清空 ComfyUI 当前的执行队列。用于中断正在进行的生成任务。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_node_info",
            "description": "查询 ComfyUI 中已安装的节点类型及其输入输出定义。用于自由组合节点构建自定义工作流。传入节点类型名可查询特定节点，不传则返回所有可用节点类型列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_type": {
                        "type": "string",
                        "description": "要查询的节点类型名，如 KSampler/CLIPTextEncode/CheckpointLoaderSimple。不传则列出所有类型。",
                    },
                    "category_filter": {
                        "type": "string",
                        "description": "按类别过滤，如 loaders/sampling/conditioning/image。不传则显示全部。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_build_custom_workflow",
            "description": "根据自定义的节点和连线描述，构建并保存 ComfyUI API 格式的工作流 JSON。支持完全自由的节点组合，不受固定模板限制。生成后可用 comfyui_submit_workflow 提交执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "JSON 数组，每个元素为节点定义：{id, class_type, inputs: {参数名: 值或[源节点id, 输出索引]}}。例如 [{id:1, class_type:'CheckpointLoaderSimple', inputs:{ckpt_name:'sd_xl_base_1.0.safetensors'}}, {id:2, class_type:'CLIPTextEncode', inputs:{text:'提示词', clip:[1,1]}}]",
                    },
                    "output_node_id": {
                        "type": "integer",
                        "description": "指定哪个节点是最终输出节点（通常是 SaveImage），用于 ComfyUI 识别输出。不传则自动找最后一个含有 images 输出的节点。",
                    },
                },
                "required": ["nodes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_create_custom_node",
            "description": "在 ComfyUI 的 custom_nodes 目录下创建一个自定义节点 Python 文件。用于扩展 ComfyUI 的功能。必须提供完整的节点类代码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {
                        "type": "string",
                        "description": "自定义节点的名称（将作为文件名和类名），如 MyImageProcessor",
                    },
                    "node_code": {
                        "type": "string",
                        "description": "完整的 Python 节点类代码，必须包含 CATEGORY/RETURN_TYPES/FUNCTION/INPUT_TYPES 定义",
                    },
                },
                "required": ["node_name", "node_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_prepare_dataset",
            "description": "为 LoRA 训练准备数据集目录结构。创建文件夹、生成标签模板文件。用户只需把训练图片放入对应文件夹即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {
                        "type": "string",
                        "description": "数据集名称（即 LoRA 名称），如 my_character_lora",
                    },
                    "concept_count": {
                        "type": "integer",
                        "description": "训练的概念数量（如 1个角色=1个概念，或 1个风格=1个概念），默认 1",
                    },
                    "concept_names": {
                        "type": "string",
                        "description": "概念名称列表，逗号分隔，如 'my_character,my_outfit'。用于创建子文件夹和触发词。",
                    },
                    "base_resolution": {
                        "type": "integer",
                        "description": "基础训练分辨率，默认 512。SD1.5推荐512，SDXL推荐1024",
                    },
                },
                "required": ["dataset_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_generate_training_config",
            "description": "生成 LoRA 训练配置文件（TOML 格式，兼容 sd-scripts/kohya_ss）。包含学习率、批次大小、训练步数、网络参数等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "数据集名称"},
                    "base_model": {
                        "type": "string",
                        "description": "基础模型路径或名称，如 sd_xl_base_1.0.safetensors 或 dreamshaper_8.safetensors",
                    },
                    "lora_type": {
                        "type": "string",
                        "description": "LoRA 类型：sdxl 或 sd15，默认根据 base_model 自动判断",
                    },
                    "learning_rate": {"type": "number", "description": "学习率，sdxl推荐1e-4，sd15推荐5e-4"},
                    "batch_size": {"type": "integer", "description": "批次大小，显存不足时减小。默认 1"},
                    "max_train_steps": {
                        "type": "integer",
                        "description": "最大训练步数。每张图建议 100-150 步。默认根据图片数自动计算",
                    },
                    "network_dim": {
                        "type": "integer",
                        "description": "LoRA网络维度，越大容量越高。角色LoRA推荐32，风格LoRA推荐64",
                    },
                    "network_alpha": {
                        "type": "integer",
                        "description": "LoRA网络alpha，通常设为network_dim的一半或相等",
                    },
                },
                "required": ["dataset_name", "base_model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_check_training_status",
            "description": "检查 LoRA 训练输出目录，查看是否有训练好的 .safetensors 文件。返回已完成的 LoRA 列表和训练日志摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "数据集名称，不传则列出所有 LoRA 训练输出"}
                },
                "required": [],
            },
        },
    },
]

# ============================================================
#  工具执行器
# ============================================================


def execute_status() -> str:
    """检查 ComfyUI 状态"""
    # 获取系统状态
    stats = _comfyui_request("/system_stats")
    if isinstance(stats, dict) and stats.get("error"):
        return json.dumps(
            {
                "available": False,
                "comfyui_url": COMFYUI_BASE_URL,
                "error": stats["error"],
                "hint": "请确保 ComfyUI 已启动。可运行 launch.py 或在 ComfyUI 目录执行 python main.py",
            },
            ensure_ascii=False,
        )

    # 获取队列状态
    queue = _comfyui_request("/queue")
    queue_running = len(queue.get("queue_running", [])) if isinstance(queue, dict) else 0
    queue_pending = len(queue.get("queue_pending", [])) if isinstance(queue, dict) else 0

    # 获取节点信息
    obj_info = _comfyui_request("/object_info")
    node_count = len(obj_info) if isinstance(obj_info, dict) else 0

    return json.dumps(
        {
            "available": True,
            "comfyui_url": COMFYUI_BASE_URL,
            "system": stats if isinstance(stats, dict) else {},
            "queue_running": queue_running,
            "queue_pending": queue_pending,
            "installed_nodes": node_count,
        },
        ensure_ascii=False,
    )


def execute_list_models() -> str:
    """列出已安装模型"""
    obj_info = _comfyui_request("/object_info")
    if not isinstance(obj_info, dict):
        return json.dumps({"error": "无法获取节点信息", "models": []}, ensure_ascii=False)

    models = {
        "checkpoints": [],  # 大模型
        "loras": [],  # LoRA
        "vae": [],  # VAE
        "controlnet": [],  # ControlNet
        "upscalers": [],  # 放大模型
        "clip": [],  # CLIP 模型
        "other": [],  # 其他
    }

    category_map = {
        "checkpoints": ["CheckpointLoader", "CheckpointLoaderSimple"],
        "loras": ["LoraLoader", "LoraLoaderModelOnly"],
        "vae": ["VAELoader"],
        "controlnet": ["ControlNetLoader", "ControlNetLoaderAdvanced"],
        "upscalers": ["UpscaleModelLoader"],
        "clip": ["CLIPLoader"],
    }

    for node_name, node_info in obj_info.items():
        if not isinstance(node_info, dict):
            continue
        input_info = node_info.get("input", {})
        if not isinstance(input_info, dict):
            continue

        for cat, loaders in category_map.items():
            if node_name in loaders:
                for _param_name, param_info in input_info.items():
                    if isinstance(param_info, (list, tuple)) and param_info:  # noqa: SIM102
                        # 检查是否是文件选择器
                        if len(param_info) >= 2:
                            choices = param_info[0] if isinstance(param_info[0], list) else []
                            for choice in choices:
                                if isinstance(choice, str) and choice not in models[cat]:
                                    models[cat].append(choice)

    total = sum(len(v) for v in models.values())
    return json.dumps(
        {
            "total_models": total,
            "models": models,
            "hint": "列出的模型可在工作流中直接使用。缺失的模型需用户手动下载到 ComfyUI models 目录。",
        },
        ensure_ascii=False,
    )


def execute_submit_workflow(workflow_json: str, wait: bool = True) -> str:
    """提交工作流并等待结果"""
    # 解析工作流 JSON
    try:
        workflow = json.loads(workflow_json) if isinstance(workflow_json, str) else workflow_json
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"工作流 JSON 格式错误: {e}", "success": False}, ensure_ascii=False)

    # 提交到 ComfyUI
    result = _comfyui_request("/prompt", method="POST", body={"prompt": workflow})
    if isinstance(result, dict) and result.get("error"):
        return json.dumps(
            {"error": result["error"], "success": False, "hint": "请确保 ComfyUI 正在运行且工作流格式正确"},
            ensure_ascii=False,
        )

    prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
    if not prompt_id:
        return json.dumps({"error": "提交失败，未获取到 prompt_id", "success": False}, ensure_ascii=False)

    if not wait:
        return json.dumps(
            {
                "success": True,
                "prompt_id": prompt_id,
                "status": "submitted",
                "hint": f"工作流已提交。稍后可通过 comfyui_get_result 查询结果，prompt_id={prompt_id}",
            },
            ensure_ascii=False,
        )

    # 轮询等待完成
    start = time.time()
    while time.time() - start < COMFYUI_TIMEOUT:
        history = _comfyui_request(f"/history/{prompt_id}")
        if isinstance(history, dict) and prompt_id in history:
            entry = history[prompt_id]
            outputs = entry.get("outputs", {})
            status_data = entry.get("status", {})

            # 检查状态
            if status_data.get("completed") is False:
                time.sleep(COMFYUI_POLL_INTERVAL)  # TODO: async 化 — 需先将此文件整体迁移到 asyncio
                continue

            # 提取输出文件
            output_files = []
            for _node_id, node_output in outputs.items():
                images = node_output.get("images", []) if isinstance(node_output, dict) else []
                for img in images:
                    fname = img.get("filename", "")
                    subfolder = img.get("subfolder", "")
                    ftype = img.get("type", "output")
                    if fname:
                        output_files.append(
                            {
                                "filename": fname,
                                "subfolder": subfolder,
                                "type": ftype,
                                "url": f"{COMFYUI_BASE_URL}/view?filename={fname}&subfolder={subfolder}&type={ftype}",
                            }
                        )

            elapsed = round(time.time() - start, 1)
            return json.dumps(
                {
                    "success": True,
                    "prompt_id": prompt_id,
                    "elapsed_seconds": elapsed,
                    "outputs": output_files,
                    "status": status_data,
                },
                ensure_ascii=False,
            )

        time.sleep(COMFYUI_POLL_INTERVAL)  # TODO: async 化 — 需先将此文件整体迁移到 asyncio

    # 超时
    return json.dumps(
        {
            "success": False,
            "prompt_id": prompt_id,
            "error": f"生成超时（已等待 {COMFYUI_TIMEOUT} 秒）",
            "hint": f"任务可能仍在进行中。稍后可手动查询: comfyui_get_result prompt_id={prompt_id}",
            "status": "timeout",
        },
        ensure_ascii=False,
    )


def submit_comfyui_workflow(workflow: dict, workflow_type: str = "image") -> dict:
    """提交工作流并等待结果，返回 dict（供 Showrunner 直接调用）。

    Args:
        workflow: 工作流参数 dict（prompt/input_images/width/height 等）
        workflow_type: "image" 或 "video"，仅用于结果字段名
    """
    raw = execute_submit_workflow(json.dumps(workflow, ensure_ascii=False), wait=True)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "ComfyUI 返回解析失败", "raw": raw[:500]}
    if workflow_type == "video":
        result.setdefault("videos", result.get("images", []))
    return result


def execute_get_result(prompt_id: str) -> str:
    """查询执行结果"""
    history = _comfyui_request(f"/history/{prompt_id}")
    if not isinstance(history, dict) or prompt_id not in history:
        # 检查是否还在队列中
        queue = _comfyui_request("/queue")
        if isinstance(queue, dict):
            for item in queue.get("queue_running", []) + queue.get("queue_pending", []):
                if isinstance(item, (list, tuple)) and len(item) > 1 and item[1] == prompt_id:
                    return json.dumps(
                        {"prompt_id": prompt_id, "status": "queued", "hint": "任务仍在队列中，请稍后重试"},
                        ensure_ascii=False,
                    )

        return json.dumps(
            {"prompt_id": prompt_id, "error": "未找到该 prompt_id 的结果", "status": "not_found"}, ensure_ascii=False
        )

    entry = history[prompt_id]
    outputs = entry.get("outputs", {})
    status_data = entry.get("status", {})

    output_files = []
    for _node_id, node_output in outputs.items():
        images = node_output.get("images", []) if isinstance(node_output, dict) else []
        for img in images:
            fname = img.get("filename", "")
            subfolder = img.get("subfolder", "")
            ftype = img.get("type", "output")
            if fname:
                output_files.append(
                    {
                        "filename": fname,
                        "url": f"{COMFYUI_BASE_URL}/view?filename={fname}&subfolder={subfolder}&type={ftype}",
                    }
                )

    return json.dumps(
        {
            "prompt_id": prompt_id,
            "status": "completed" if status_data.get("completed") is not False else "running",
            "outputs": output_files,
            "meta": status_data,
        },
        ensure_ascii=False,
    )


def execute_preview_workflow(workflow_json: str) -> str:
    """将工作流加载到 ComfyUI 画布预览"""
    try:
        workflow = json.loads(workflow_json) if isinstance(workflow_json, str) else workflow_json
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"工作流 JSON 格式错误: {e}", "success": False}, ensure_ascii=False)

    # 使用 ComfyUI 的 /api/upload/image 端点来接收画布格式的工作流
    # 或发送到 Agent Bridge 的自定义端点
    try:
        _comfyui_request(
            "/api/agent-bridge/workflow", method="POST", body={"workflow": workflow, "action": "preview"}, timeout=10
        )
        return json.dumps(
            {"success": True, "message": "工作流已发送到 ComfyUI 画布", "hint": "在 ComfyUI 界面中查看加载的工作流"},
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        # 如果不支持 bridge，返回 JSON 让用户手动加载
        return json.dumps(
            {
                "success": False,
                "error": "未检测到 ComfyUI Agent Bridge 扩展",
                "hint": "请手动将以下工作流 JSON 拖入 ComfyUI 画布，或安装 comfyui_agent_bridge 扩展",
                "workflow_preview": json.dumps(workflow, ensure_ascii=False)[:2000],
            },
            ensure_ascii=False,
        )


def execute_clear_queue() -> str:
    """清空 ComfyUI 队列"""
    _comfyui_request("/queue", method="POST", body={"clear": True})
    queue_after = _comfyui_request("/queue")

    running = len(queue_after.get("queue_running", [])) if isinstance(queue_after, dict) else 0
    pending = len(queue_after.get("queue_pending", [])) if isinstance(queue_after, dict) else 0

    return json.dumps(
        {"success": True, "message": "队列已清空", "remaining_running": running, "remaining_pending": pending},
        ensure_ascii=False,
    )


def execute_get_node_info(node_type: str = "", category_filter: str = "") -> str:
    """查询已安装节点的类型定义。

    ComfyUI /object_info 返回 {NodeClassName: {input: {required: {...}, optional: {...}},
    output: [...], output_is_list: [...], output_name: [...], category: ...}}

    本函数提取关键信息以供 CRUX 自由编排工作流。
    """
    obj_info = _comfyui_request("/object_info")
    if not isinstance(obj_info, dict):
        return json.dumps({"error": "无法获取节点信息"}, ensure_ascii=False)

    # 如果指定了具体节点类型
    if node_type:
        info = obj_info.get(node_type)
        if not info:
            # 尝试模糊匹配
            matches = [k for k in obj_info if node_type.lower() in k.lower()]
            if matches:
                return json.dumps(
                    {
                        "query": node_type,
                        "matches": matches[:20],
                        "hint": "以上为匹配的节点类型，请选择具体类型重新查询",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {"error": f"未找到节点类型: {node_type}", "available_count": len(obj_info)}, ensure_ascii=False
            )

        return json.dumps(_simplify_node_info(node_type, info), ensure_ascii=False)

    # 返回所有节点的摘要列表（分类组织）
    categories: dict[str, list[str]] = {}
    for cls_name, cls_info in obj_info.items():
        if not isinstance(cls_info, dict):
            continue
        cat = cls_info.get("category", "other")
        categories.setdefault(cat, []).append(cls_name)

    # 如果指定了类别过滤
    if category_filter:
        filtered = {k: v for k, v in categories.items() if category_filter.lower() in k.lower()}
        return json.dumps(
            {
                "categories": {k: sorted(v) for k, v in filtered.items()},
                "total_nodes": sum(len(v) for v in filtered.values()),
                "hint": "使用 comfyui_get_node_info node_type='具体类型名' 查看节点输入输出详情",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "total_nodes": sum(len(v) for v in categories.values()),
            "categories": {k: sorted(v) for k, v in sorted(categories.items())},
            "hint": "使用 comfyui_get_node_info node_type='具体类型名' 查看节点输入输出详情",
        },
        ensure_ascii=False,
    )


def _simplify_node_info(cls_name: str, info: dict) -> dict:
    """简化节点信息，提取输入输出关键字段"""
    result: dict = {
        "class_type": cls_name,
        "category": info.get("category", "unknown"),
        "display_name": info.get("display_name", cls_name),
        "description": info.get("description", ""),
    }

    # 提取输入
    inputs = info.get("input", {})
    if isinstance(inputs, dict):
        required = inputs.get("required", {})
        optional = inputs.get("optional", {})

        def _fmt_param(pname: str, pconfig: list) -> dict:
            """将 ComfyUI 参数格式化为可读结构"""
            ptype = "unknown"
            choices = None
            default = None
            min_val = max_val = None

            if isinstance(pconfig, (list, tuple)):
                if len(pconfig) >= 1:
                    ptype = str(pconfig[0]) if not isinstance(pconfig[0], list) else "combo"
                    if isinstance(pconfig[0], list):
                        choices = pconfig[0]
                if len(pconfig) >= 2:
                    default = pconfig[1]
                if len(pconfig) >= 3:
                    d = pconfig[2] if isinstance(pconfig[2], dict) else {}
                    min_val = d.get("min")
                    max_val = d.get("max")

            return {"type": ptype, "choices": choices, "default": default, "min": min_val, "max": max_val}

        result["inputs"] = {
            "required": {k: _fmt_param(k, v) for k, v in required.items()},
            "optional": {k: _fmt_param(k, v) for k, v in optional.items()},
        }

    # 提取输出
    output = info.get("output", [])
    output_name = info.get("output_name", [])
    output_is_list = info.get("output_is_list", [])

    result["outputs"] = [
        {
            "index": i,
            "type": output[i] if i < len(output) else "unknown",
            "name": output_name[i] if i < len(output_name) else f"output_{i}",
            "is_list": output_is_list[i] if i < len(output_is_list) else False,
        }
        for i in range(len(output))
    ]

    return result


def execute_build_custom_workflow(nodes: str, output_node_id: int = -1) -> str:
    """根据节点描述构建 ComfyUI API 格式的工作流 JSON。

    节点格式：
    [
      {
        "id": 1,
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}
      },
      {
        "id": 2,
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "a beautiful landscape", "clip": [1, 1]}
      }
    ]

    inputs 中的值可以是：
    - 字面值（字符串/数字/布尔）
    - [源节点id, 输出索引] 表示连线
    """
    try:
        nodes_list = json.loads(nodes) if isinstance(nodes, str) else nodes
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"节点 JSON 格式错误: {e}", "success": False}, ensure_ascii=False)

    if not isinstance(nodes_list, list):
        return json.dumps({"error": "nodes 必须是 JSON 数组", "success": False}, ensure_ascii=False)

    # 构建工作流
    workflow = {}
    node_ids = []
    save_image_id = None

    for node in nodes_list:
        nid = str(node["id"])
        node_ids.append(nid)
        class_type = node["class_type"]
        raw_inputs = node.get("inputs", {})

        # 转换 inputs：自动展开 [源id, 输出索引] 为连线引用
        inputs_converted = {}
        for k, v in raw_inputs.items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, str)):
                # 连线引用：[源节点ID, 输出槽]
                inputs_converted[k] = [str(v[0]), v[1]]
            else:
                inputs_converted[k] = v

        workflow[nid] = {"class_type": class_type, "inputs": inputs_converted}

        # 追踪 SaveImage 类节点作为默认输出
        if "save" in class_type.lower() or "preview" in class_type.lower():
            save_image_id = nid

    # 确定输出节点
    final_output = str(output_node_id) if output_node_id >= 0 else save_image_id or node_ids[-1]

    # 保存到输出目录
    out_dir = OUTPUT_ROOT / "workflows"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    file_path = out_dir / f"custom_workflow_{timestamp}.json"
    file_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "success": True,
            "workflow": workflow,
            "saved_path": str(file_path),
            "node_count": len(node_ids),
            "output_node_id": final_output,
            "node_ids": node_ids,
            "hint": f"工作流已构建(共{len(node_ids)}个节点)。用 comfyui_submit_workflow 提交执行。",
        },
        ensure_ascii=False,
    )


def execute_create_custom_node(node_name: str, node_code: str) -> str:
    """在 ComfyUI custom_nodes 目录下创建自定义节点文件。

    节点代码必须是一个完整的 Python 类，继承自 ComfyUI 节点基类。
    必须包含：CATEGORY, RETURN_TYPES, FUNCTION, INPUT_TYPES 类属性。
    """
    # 确定 custom_nodes 目录
    if COMFYUI_CUSTOM_NODES_DIR:
        custom_nodes = Path(COMFYUI_CUSTOM_NODES_DIR)
    else:
        # 尝试从环境推断：ComfyUI 通常位于 base_url 对应目录的上一级
        # 简单回退到用户配置
        return json.dumps(
            {
                "error": "未配置 COMFYUI_CUSTOM_NODES_DIR 环境变量",
                "hint": "请设置环境变量 COMFYUI_CUSTOM_NODES_DIR 指向 ComfyUI 的 custom_nodes 目录",
                "success": False,
            },
            ensure_ascii=False,
        )

    if not custom_nodes.exists():
        return json.dumps({"error": f"custom_nodes 目录不存在: {custom_nodes}", "success": False}, ensure_ascii=False)

    # 验证代码包含必要元素
    required_attrs = ["CATEGORY", "RETURN_TYPES", "FUNCTION", "INPUT_TYPES"]
    missing = [a for a in required_attrs if a not in node_code]
    if missing:
        return json.dumps(
            {
                "error": f"节点代码缺少必要属性: {missing}",
                "required": "必须包含 CATEGORY, RETURN_TYPES, FUNCTION, INPUT_TYPES",
                "success": False,
            },
            ensure_ascii=False,
        )

    # 写入文件
    safe_name = node_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    node_file = custom_nodes / f"{safe_name}.py"

    if node_file.exists():
        return json.dumps(
            {
                "error": f"节点文件已存在: {node_file}",
                "hint": "请使用不同的节点名称，或手动删除旧文件后重试",
                "success": False,
            },
            ensure_ascii=False,
        )

    node_file.write_text(node_code, encoding="utf-8")

    return json.dumps(
        {
            "success": True,
            "node_name": safe_name,
            "file_path": str(node_file),
            "hint": "自定义节点已创建。重启 ComfyUI 后生效。",
        },
        ensure_ascii=False,
    )


# ============================================================
#  LoRA 训练工具执行器
# ============================================================

LORA_OUTPUT_ROOT = OUTPUT_ROOT / "lora_training"
LORA_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def execute_lora_prepare_dataset(
    dataset_name: str, concept_count: int = 1, concept_names: str = "", base_resolution: int = 512
) -> str:
    """准备 LoRA 训练数据集目录结构

    目录结构：
    lora_training/
      my_lora/
        dataset/
          concept_1/        ← 放训练图片
            1.png
            2.png
            1.txt           ← 标签文件（可选）
          concept_2/        ← 第二个概念
          ...
        config/
          dataset.toml      ← 训练配置（由 lora_generate_training_config 生成）
        output/             ← 训练输出目录
    """
    safe_name = dataset_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    ds_root = LORA_OUTPUT_ROOT / safe_name

    # 解析概念名称
    names = [n.strip() for n in concept_names.split(",") if n.strip()] if concept_names else [safe_name]
    concept_count = max(concept_count, len(names))

    created_dirs = []
    concept_info = []

    for i in range(concept_count):
        cname = names[i] if i < len(names) else f"concept_{i + 1}"
        # 每个概念一个图片文件夹
        img_dir = ds_root / "dataset" / cname
        img_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(str(img_dir))

        # 生成标签模板
        tag_template = (
            f"# 为每张训练图创建同名的 .txt 标签文件\n# 内容：描述图片的文字，触发词会自动添加\n# 触发词: {cname}\n"
        )
        (img_dir / "README.txt").write_text(tag_template, encoding="utf-8")

        concept_info.append(
            {"name": cname, "image_dir": str(img_dir), "trigger_word": cname, "resolution": base_resolution}
        )

    # 创建配置和输出目录
    config_dir = ds_root / "config"
    output_dir = ds_root / "output"
    config_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return json.dumps(
        {
            "success": True,
            "dataset_name": safe_name,
            "root_dir": str(ds_root),
            "concepts": concept_info,
            "config_dir": str(config_dir),
            "output_dir": str(output_dir),
            "steps": {
                "1": "把训练图片放入各概念文件夹（建议每概念10-50张图）",
                "2": "为每张图创建同名 .txt 标签文件，描述画面内容",
                "3": f"触发词 {[c['trigger_word'] for c in concept_info]} 会自动添加到训练中",
                "4": "准备完毕后调用 lora_generate_training_config 生成训练配置",
                "5": "最后运行 sd-scripts 或 kohya_ss 开始训练",
            },
            "tips": {
                "image_count": "每概念建议 10-50 张图，太少会过拟合，太多训练时间过长",
                "image_quality": "图片清晰、多样化（不同角度/光照/表情/背景）效果更好",
                "captions": "标签描述画面内容即可，不要重复触发词（脚本会自动加）",
                "resolution": f"图片会自动裁剪/缩放为 {base_resolution}x{base_resolution}",
            },
        },
        ensure_ascii=False,
    )


def execute_lora_generate_config(
    dataset_name: str,
    base_model: str,
    lora_type: str = "",
    learning_rate: float = 0,
    batch_size: int = 1,
    max_train_steps: int = 0,
    network_dim: int = 32,
    network_alpha: int = 16,
) -> str:
    """生成 sd-scripts/kohya_ss 兼容的 LoRA 训练 TOML 配置"""
    safe_name = dataset_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    ds_root = LORA_OUTPUT_ROOT / safe_name

    if not ds_root.exists():
        return json.dumps(
            {"error": f"数据集不存在: {ds_root}。请先调用 lora_prepare_dataset", "success": False}, ensure_ascii=False
        )

    # 自动推断 LoRA 类型
    if not lora_type:
        base_lower = base_model.lower()
        lora_type = "sdxl" if any(k in base_lower for k in ["sdxl", "xl", "sd_xl"]) else "sd15"

    # 自动设置学习率
    if learning_rate <= 0:
        learning_rate = 1e-4 if lora_type == "sdxl" else 5e-4

    # 自动设置训练步数
    if max_train_steps <= 0:
        # 尝试统计图片数量
        img_count = 0
        for concept_dir in (ds_root / "dataset").iterdir():
            if concept_dir.is_dir():
                imgs = (
                    list(concept_dir.glob("*.png")) + list(concept_dir.glob("*.jpg")) + list(concept_dir.glob("*.webp"))
                )
                img_count += len(imgs)
        max_train_steps = max(500, img_count * 120) if img_count > 0 else 1500

    # 查找实际存在的 concept 目录
    dataset_dir = ds_root / "dataset"
    concepts = [d.name for d in sorted(dataset_dir.iterdir()) if d.is_dir() and not d.name.startswith("_")]

    if not concepts:
        return json.dumps(
            {"error": f"数据集中没有概念文件夹。请在 {dataset_dir} 下创建子文件夹并放入训练图片。", "success": False},
            ensure_ascii=False,
        )

    # 构建 dataset 配置块
    dataset_blocks = []
    for _i, cname in enumerate(concepts):
        ds_block = (
            f"[[datasets.subsets]]\n"
            f'  image_dir = "dataset/{cname}"\n'
            f'  class_tokens = "{cname}"\n'
            f"  num_repeats = 1\n"
            f"  is_reg = false\n"
        )
        dataset_blocks.append(ds_block)

    # 完整 TOML 配置
    config_dir = ds_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_content = f"""# LoRA Training Config — generated by CRUX ComfyUI Bridge
# 兼容: sd-scripts (kohya_ss) / onetrainer

[general]
enable_bucket = true
bucket_no_upscale = true
bucket_reso_steps = 64
min_bucket_reso = 256
max_bucket_reso = 2048 if lora_type == "sdxl" else 1024
caption_extension = ".txt"
shuffle_caption = true
keep_tokens = 0
flip_aug = true
color_aug = false
face_crop_aug_range = ""
random_crop = false
cache_latents = true
cache_latents_to_disk = true

[dataset]
resolution = [1024, 1024] if lora_type == "sdxl" else [512, 512]
enable_bucket = true
batch_size = {batch_size}
num_repeats = 1

{chr(10).join(dataset_blocks)}
[network]
type = "lora"
conv_dim = {network_dim}
conv_alpha = {network_alpha}
network_dropout = 0.1
rank_dropout = 0.1

[optimizer]
optimizer_type = "AdamW8bit"
learning_rate = {learning_rate}
lr_scheduler = "cosine"
lr_warmup_steps = 100
max_train_steps = {max_train_steps}
save_every_n_steps = {max(max_train_steps // 5, 100)}
save_precision = "fp16"

[saving]
output_dir = "output"
output_name = "{safe_name}"
save_model_as = "safetensors"

[logging]
log_with = "tensorboard"
logging_dir = "logs"

[model]
pretrained_model_name_or_path = "{base_model}"
vae = ""
v2 = false
tokenizer_cache_dir = ""

# ── 使用说明 ──
# 运行方式1 (sd-scripts):
#   accelerate launch sd-scripts/train_network.py --config_file=config/{safe_name}.toml
#
# 运行方式2 (kohya_ss GUI):
#   在 kohya_ss Web UI 中导入此配置文件
#
# 运行方式3 (onetrainer):
#   onetrainer --config config/{safe_name}.toml
"""

    config_path = config_dir / f"{safe_name}.toml"
    config_path.write_text(config_content, encoding="utf-8")

    return json.dumps(
        {
            "success": True,
            "config_path": str(config_path),
            "config_summary": {
                "lora_type": lora_type,
                "base_model": base_model,
                "learning_rate": f"{learning_rate:.1e}",
                "batch_size": batch_size,
                "max_train_steps": max_train_steps,
                "network_dim": network_dim,
                "network_alpha": network_alpha,
                "concepts": concepts,
                "approximate_time": f"约 {max_train_steps * 2 // 60} 分钟 (取决于 GPU)",
            },
            "run_commands": [
                "# 方式1: sd-scripts 命令行",
                f"accelerate launch sd-scripts/train_network.py --config_file={config_path}",
                "",
                "# 方式2: kohya_ss GUI 导入",
                f"在 kohya_ss 的 LoRA 训练页面导入: {config_path}",
                "",
                "# 方式3: 先检查训练工具是否安装",
                "pip show sd-scripts  # 或 kohya_ss",
            ],
        },
        ensure_ascii=False,
    )


def execute_lora_check_status(dataset_name: str = "") -> str:
    """检查 LoRA 训练状态"""
    if dataset_name:
        safe_name = dataset_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        ds_root = LORA_OUTPUT_ROOT / safe_name
        if not ds_root.exists():
            return json.dumps({"dataset_name": safe_name, "exists": False, "error": "数据集不存在"}, ensure_ascii=False)

        output_dir = ds_root / "output"
        if not output_dir.exists():
            return json.dumps(
                {
                    "dataset_name": safe_name,
                    "status": "not_started",
                    "output_dir": str(output_dir),
                    "hint": "训练尚未开始或输出目录不存在",
                },
                ensure_ascii=False,
            )

        # 检查训练产出
        safetensors = list(output_dir.rglob("*.safetensors"))
        return json.dumps(
            {
                "dataset_name": safe_name,
                "status": "completed" if safetensors else "training_or_failed",
                "trained_loras": [
                    {"name": s.name, "size_mb": round(s.stat().st_size / 1024 / 1024, 1), "path": str(s)}
                    for s in sorted(safetensors)
                ],
                "total_safetensors": len(safetensors),
            },
            ensure_ascii=False,
        )

    # 列出所有训练项目
    all_projects = []
    for ds_dir in sorted(LORA_OUTPUT_ROOT.iterdir()):
        if not ds_dir.is_dir():
            continue
        output_dir = ds_dir / "output"
        safetensors = list(output_dir.rglob("*.safetensors")) if output_dir.exists() else []
        config_files = list((ds_dir / "config").glob("*.toml")) if (ds_dir / "config").exists() else []

        all_projects.append(
            {
                "name": ds_dir.name,
                "has_config": len(config_files) > 0,
                "trained_count": len(safetensors),
                "trained_loras": [s.name for s in safetensors],
                "status": "completed" if safetensors else ("configured" if config_files else "dataset_only"),
            }
        )

    return json.dumps(
        {"total_projects": len(all_projects), "projects": all_projects, "output_root": str(LORA_OUTPUT_ROOT)},
        ensure_ascii=False,
    )


# ============================================================
#  工具名称 → 执行函数 映射表
# ============================================================

COMFYUI_EXECUTOR_MAP = {
    "comfyui_status": lambda **kw: execute_status(),
    "comfyui_list_models": lambda **kw: execute_list_models(),
    "comfyui_submit_workflow": lambda **kw: execute_submit_workflow(
        workflow_json=kw.get("workflow_json", "{}"), wait=kw.get("wait", True)
    ),
    "comfyui_get_result": lambda **kw: execute_get_result(prompt_id=kw.get("prompt_id", "")),
    "comfyui_preview_workflow": lambda **kw: execute_preview_workflow(workflow_json=kw.get("workflow_json", "{}")),
    "comfyui_clear_queue": lambda **kw: execute_clear_queue(),
    "comfyui_get_node_info": lambda **kw: execute_get_node_info(
        node_type=kw.get("node_type", ""), category_filter=kw.get("category_filter", "")
    ),
    "comfyui_build_custom_workflow": lambda **kw: execute_build_custom_workflow(
        nodes=kw.get("nodes", "[]"), output_node_id=kw.get("output_node_id", -1)
    ),
    "comfyui_create_custom_node": lambda **kw: execute_create_custom_node(
        node_name=kw.get("node_name", ""), node_code=kw.get("node_code", "")
    ),
    "lora_prepare_dataset": lambda **kw: execute_lora_prepare_dataset(
        dataset_name=kw.get("dataset_name", "untitled"),
        concept_count=kw.get("concept_count", 1),
        concept_names=kw.get("concept_names", ""),
        base_resolution=kw.get("base_resolution", 512),
    ),
    "lora_generate_training_config": lambda **kw: execute_lora_generate_config(
        dataset_name=kw.get("dataset_name", ""),
        base_model=kw.get("base_model", "sd_xl_base_1.0.safetensors"),
        lora_type=kw.get("lora_type", ""),
        learning_rate=kw.get("learning_rate", 0),
        batch_size=kw.get("batch_size", 1),
        max_train_steps=kw.get("max_train_steps", 0),
        network_dim=kw.get("network_dim", 32),
        network_alpha=kw.get("network_alpha", 16),
    ),
    "lora_check_training_status": lambda **kw: execute_lora_check_status(dataset_name=kw.get("dataset_name", "")),
    # tools.json 兼容别名 (避免 comfyui_lora_* vs lora_* 命名冲突)
    "comfyui_lora_prepare": lambda **kw: execute_lora_prepare_dataset(
        dataset_name=kw.get("dataset_name", "untitled"),
        concept_count=kw.get("concept_count", 1),
        concept_names=kw.get("concept_names", ""),
        base_resolution=kw.get("base_resolution", 512),
    ),
    "comfyui_lora_generate_config": lambda **kw: execute_lora_generate_config(
        dataset_name=kw.get("dataset_name", ""),
        base_model=kw.get("base_model", "sd_xl_base_1.0.safetensors"),
        resolution=kw.get("resolution", "1024,1024"),  # pyright: ignore[reportCallIssue]
        learning_rate=kw.get("learning_rate", "0.0001"),
        batch_size=kw.get("batch_size", 1),
        max_train_steps=kw.get("max_train_steps", 1000),
        network_dim=kw.get("network_dim", 32),
        network_alpha=kw.get("network_alpha", 16),
    ),
    "comfyui_lora_check_status": lambda **kw: execute_lora_check_status(dataset_name=kw.get("dataset_name", "")),
}
