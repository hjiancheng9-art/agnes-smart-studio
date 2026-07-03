"""智能体工具注册与执行系统

让 crux-smart-studio 作为主脑，调用和管理外部工具/脚本/API。
工具可从 tools.json 配置文件加载，也可通过 Python API 动态注册。

结构:
    tools.json         ← 用户定义的工具清单
    core/tools.py      ← 本文件：注册、执行、格式转换

工具类型:
    "shell"    - 执行本地命令，返回 stdout
    "http"     - 调用 HTTP API，返回响应
    "python"   - 调用 Python 函数（import 路径）
    "pipeline" - 一键流视频管道工具（Showrunner 专用）
"""

import importlib
import json
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

TOOLS_CONFIG = Path(__file__).parent.parent / "tools.json"


# ── 轻量 no-op 上下文管理器（observability 不可用时降级）──
@contextmanager
def _noop_cm():
    """Yield None, no-op.  Used when core.observability is not importable."""
    yield None


__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "BUILTIN_TOOLS",
    "CORE_TOOL_NAMES",
    "COMFYUI_TOOL_DEFS",
    "PIPELINE_TOOL_DEFS",
    "TOOLS_CONFIG",
    "TOOL_EXPANSION_CATEGORIES",
    "ToolRegistry",
    "_resolve_tool_names",
    "get_registry",
    "reload_registry",
]


# ── 内置工具定义（生图/生视频，从 chat.py 移出）──

BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Create an image from text. Supports text-to-image, image-to-image (image_url), and multi-image reference (image_urls array).",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Image description including style, lighting, composition, and negative constraints",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "Optional single reference image URL/path for image-to-image editing",
                    },
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional multiple reference image URLs for multi-image guided generation",
                    },
                    "size": {
                        "type": "string",
                        "enum": [
                            "1024x768",
                            "1024x1024",
                            "768x1024",
                            "576x1024",
                            "1024x576",
                            "448x1024",
                            "1024x448",
                            "684x1024",
                            "1024x684",
                        ],
                        "description": "Image size (WxH). Default 1024x768.",
                    },
                    "seed": {"type": "integer", "description": "Optional random seed for reproducibility"},
                    "system": {
                        "type": "string",
                        "description": "Optional style preset: cinematic, anime, watercolor, cyberpunk, fantasy, product, portrait, landscape",
                    },
                    "negative_prompt": {"type": "string", "description": "What to avoid in the generated image"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": "Create a video from text or images. Modes: text-to-video, image-to-video, keyframe animation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Video content / motion / transition description"},
                    "image_url": {"type": "string", "description": "Optional single image URL for image-to-video mode"},
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional array of image URLs for multi-image video or keyframe animation",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["ti2vid", "keyframes"],
                        "description": "Generation mode: ti2vid (text/image-to-video, default), keyframes (smooth transition between images)",
                    },
                    "size": {
                        "type": "string",
                        "enum": ["1152x768", "1280x720", "720x1280", "1024x1024", "1024x768", "768x1024"],
                        "description": "Video size (WxH). Default 1152x768.",
                    },
                    "num_frames": {
                        "type": "integer",
                        "enum": [81, 121, 161, 201, 241, 281, 321, 361, 401, 441],
                        "description": "Video frames (8n+1). Default 121 (5.0s at 24fps). Max 441 (18.4s).",
                    },
                    "frame_rate": {
                        "type": "integer",
                        "description": "Frame rate 1-60. Default 24, use 30 for smoother motion.",
                    },
                    "seed": {"type": "integer", "description": "Optional random seed for reproducible results"},
                    "system": {
                        "type": "string",
                        "description": "Optional style preset: cinematic, anime, watercolor, cyberpunk, fantasy",
                    },
                    "negative_prompt": {"type": "string", "description": "What to avoid in the generated video"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "multi_agent",
            "description": "多智能体协调：将复杂目标分解为多个子任务，并行派发给多个 agent 协同完成。适用于代码审查、调试排查、架构分析等需要多步骤并行的场景。返回各子任务执行结果汇总。",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "需要多智能体协同完成的目标描述"},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trm_route",
            "description": "TRM (Tool Registry Mesh) 智能工具路由：根据任务意图自动选择最优工具链并执行。支持自动 fallback。intent: search(代码搜索)/review(代码审查)/execute(编码实现)/think(深度分析)/generate(媒体生成)/status(状态检查)。query/prompt/target 等参数会传递给选中的工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["search", "review", "execute", "think", "generate", "status"],
                        "description": "任务意图类型",
                    },
                    "query": {"type": "string", "description": "search/review 用的搜索/审查目标"},
                    "prompt": {"type": "string", "description": "execute/think 用的任务描述"},
                    "target": {"type": "string", "description": "review/search 的文件/目录路径"},
                    "plan": {"type": "string", "description": "execute 用的实现计划"},
                    "work_dir": {"type": "string", "description": "工作目录（默认当前项目根）"},
                    "timeout": {"type": "integer", "description": "超时秒数（默认根据 intent 自动选择）"},
                },
                "required": ["intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trm_growth",
            "description": "查看 CRUX 成长引擎状态：总调用次数、每个意图的优化路由排序、各工具的成功率/延迟/降级状态。展示 CRUX 从每次调用中学到了什么。",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["search", "review", "execute", "think", "generate", "status"],
                        "description": "按意图筛选（不传则显示全部）",
                    },
                    "reset": {"type": "boolean", "description": "重置成长数据（危险操作）"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trm_tune",
            "description": "CRUX 内秀优化：自动分析成长数据，检测瓶颈，生成自优化建议。CRUX 从每次调用中学到的经验用于优化自身参数和路由策略。返回自调参结果、瓶颈检测和改进建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "apply": {"type": "boolean", "description": "是否自动应用调参建议（默认 false，仅分析）"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trm_catalog",
            "description": "查看 TRM 工具目录：列出七兽网格中所有可用工具及其分类、来源、路由规则。不执行任何操作，仅返回目录信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["search", "review", "execute", "think", "generate", "status"],
                        "description": "按分类筛选（不传则显示全部）",
                    },
                    "source": {"type": "string", "description": "按来源筛选 (crux/codex/kimi/qoder/codebuddy)"},
                },
                "required": [],
            },
        },
    },
]

# ── 管道工具定义（Showrunner 总控脑专用）──
# 这些工具在加载 showrunner 技能时自动注册到 ToolRegistry

PIPELINE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "extract_video_keyframes",
            "description": "从本地视频文件提取关键帧画面。返回帧文件路径列表和视频元信息。提取后立即用视觉理解分析每帧内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "本地视频文件的完整路径"},
                    "max_frames": {
                        "type": "integer",
                        "description": "最多提取的关键帧数量，默认 12",
                    },
                },
                "required": ["video_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_project_manifest",
            "description": "保存项目生产清单（资产/分镜/文案/进度），用于断点续传和进度跟踪。在每个生产阶段完成后调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                    "manifest": {
                        "type": "object",
                        "description": "项目清单 JSON，包含 phase/stage/assets/shots/script 等字段",
                    },
                },
                "required": ["project_name", "manifest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_file_exists",
            "description": "检查文件是否存在，用于验证资产/关键帧/视频是否已生成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "要检查的文件路径"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "列出项目输出目录中的所有文件，用于进度检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url_content",
            "description": "获取在线URL的页面信息（标题、描述、媒体类型），用于处理视频链接输入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要获取内容的在线 URL"},
                },
                "required": ["url"],
            },
        },
    },
]

# ── ComfyUI 桥接工具定义（ComfyUI Bridge 专用）──
# 这些工具在加载 comfyui-bridge 技能时自动注册到 ToolRegistry

COMFYUI_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "comfyui_status",
            "description": "检查 ComfyUI 服务是否在线，获取队列状态和已安装节点数。生成工作流前先调用此工具。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_list_models",
            "description": "列出 ComfyUI 中已安装的模型（大模型/LoRA/VAE/ControlNet）。构建工作流前确认所需模型存在。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_node_info",
            "description": "查询 ComfyUI 已安装节点的类型、输入输出定义。用于自由编排自定义工作流。不传参返回所有节点分类列表，传 node_type 查看具体节点的接线定义。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_type": {
                        "type": "string",
                        "description": "要查询的节点类型名，如 KSampler。不传列出所有类型。",
                    },
                    "category_filter": {
                        "type": "string",
                        "description": "按类别过滤，如 loaders/sampling/conditioning。",
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
            "description": "自由组合任意节点构建自定义工作流 JSON。传入节点数组描述（id/class_type/inputs），返回可提交执行的工作流。不受固定模板限制。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {"type": "string", "description": "JSON 数组的节点描述，每节点含 id/class_type/inputs。"},
                    "output_node_id": {"type": "integer", "description": "输出节点 ID，不传自动推断。"},
                },
                "required": ["nodes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_create_custom_node",
            "description": "在 ComfyUI custom_nodes 目录创建自定义节点 Python 文件，扩展新功能。需设置 COMFYUI_CUSTOM_NODES_DIR 环境变量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {"type": "string", "description": "自定义节点名称（文件名和类名）"},
                    "node_code": {
                        "type": "string",
                        "description": "完整 Python 节点类代码，含 CATEGORY/RETURN_TYPES/FUNCTION/INPUT_TYPES",
                    },
                },
                "required": ["node_name", "node_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_submit_workflow",
            "description": "提交工作流 JSON 到 ComfyUI 执行队列，等待并返回生成结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {"type": "string", "description": "ComfyUI API 格式的工作流 JSON"},
                    "wait": {"type": "boolean", "description": "是否等待完成，默认 true"},
                },
                "required": ["workflow_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_result",
            "description": "通过 prompt_id 查询 ComfyUI 工作流的执行结果。用于异步提交后查询。",
            "parameters": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string", "description": "提交时返回的 prompt_id"}},
                "required": ["prompt_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_preview_workflow",
            "description": "将工作流 JSON 发送到 ComfyUI 画布预览，不提交执行。",
            "parameters": {
                "type": "object",
                "properties": {"workflow_json": {"type": "string", "description": "画布格式的工作流 JSON"}},
                "required": ["workflow_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_clear_queue",
            "description": "清空 ComfyUI 当前执行队列，中断正在进行的生成任务。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_prepare_dataset",
            "description": "为 LoRA 训练准备数据集目录。创建文件夹结构、生成标签模板。用户只需放入训练图片即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "LoRA 名称"},
                    "concept_count": {"type": "integer", "description": "概念数量，默认1"},
                    "concept_names": {"type": "string", "description": "概念名逗号分隔，如 '角色,服装'"},
                    "base_resolution": {"type": "integer", "description": "基础分辨率，SD1.5=512, SDXL=1024"},
                },
                "required": ["dataset_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_generate_training_config",
            "description": "生成 sd-scripts/kohya_ss 兼容的 LoRA 训练 TOML 配置文件。含学习率、batch、步数等全参数。自动根据模型类型和图片数推算最佳值。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "数据集名称"},
                    "base_model": {"type": "string", "description": "基础模型路径"},
                    "lora_type": {"type": "string", "description": "sdxl 或 sd15"},
                    "learning_rate": {"type": "number", "description": "学习率，空则自动"},
                    "batch_size": {"type": "integer", "description": "batch大小，默认1"},
                    "max_train_steps": {"type": "integer", "description": "最大步数，空则自动"},
                    "network_dim": {"type": "integer", "description": "网络维度，角色32/风格64"},
                    "network_alpha": {"type": "integer", "description": "网络alpha，通常dim的一半"},
                },
                "required": ["dataset_name", "base_model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lora_check_training_status",
            "description": "检查 LoRA 训练输出目录，查看已训练好的 .safetensors 文件。",
            "parameters": {
                "type": "object",
                "properties": {"dataset_name": {"type": "string", "description": "数据集名，不传列出全部"}},
                "required": [],
            },
        },
    },
]

# ── 通用代理系统提示 ──

AGENT_SYSTEM_PROMPT = """你是 {provider_name} 智能体，当前运行在 {model_name} 模型上。你可以调用多种工具来完成任务：

- **内置工具**: generate_image / generate_video
- **外部工具**: 由 tools.json 配置文件定义（shell脚本、HTTP API、Python函数）

规则：
1. 分析用户需求，选择合适的工具
2. 一次可调用多个工具，但不要过度调用
3. 工具执行结果会返回给你，你再据此给出回答
4. 如果工具失败，报告错误并尝试其他方案
5. 普通对话不调用工具
6. generate_image / generate_video 每轮最多调用 1 次，生成后必须直接总结结果，不要再调用其他工具
7. 严禁在生成后进行对比评估并重新生成"""


# ── 工具分类映射（按模块前缀归类，用于 system prompt 分组显示）──
# 顺序即展示顺序；emoji + 分类名 → (模块前缀元组, 显式工具名集合)
# 显式工具名优先于前缀匹配（处理 web_fetch/web_search 等跨模块工具）
TOOL_CATEGORIES: list[tuple[str, tuple[str, ...], frozenset[str]]] = [
    ("🎨 生成", ("",), frozenset({"generate_image", "generate_video", "imagegen"})),
    ("📁 文件", ("core.file_tools",), frozenset()),
    ("🌐 联网", ("",), frozenset({"web_fetch", "web_search"})),
    ("🔧 Git", ("core.git_tools", "core.git_workflow"), frozenset()),
    ("🐙 GitHub", ("core.github_tools",), frozenset()),
    ("🔍 代码智能", ("core.code_intel", "core.rag", "core.lsp"), frozenset()),
    ("📝 文档", ("core.codex_tools",), frozenset()),
    ("🤖 自动化", ("core.codex_engines",), frozenset()),
    ("🎬 流水线", ("core.pipeline_tools",), frozenset()),
    ("🧩 ComfyUI", ("core.comfyui_tools",), frozenset()),
    ("🌐 网页生成", ("core.browser_tools",), frozenset()),
    ("📓 Notebook", ("core.notebook",), frozenset()),
    ("🎵 音频", ("core.audio_tools",), frozenset()),
    ("🔌 MCP 桥接", ("core.mcp_client",), frozenset()),
]

# 工具名 → 模块路径的辅助映射（load() 时填充，供分类查询）
# builtin 工具无模块路径，用特殊标记
_BUILTIN_MODULE = "__builtin__"


# ── #4 工具错误自动恢复：参数校验 + 相似工具建议 ──────────────────────

# Python 类型 → JSON schema 类型名映射
_PY_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _validate_args(name: str, args: dict, definitions: list[dict]) -> tuple[bool, str]:
    """前置参数校验：检查 required 字段存在性 + 基本类型匹配（#4）。

    从 definitions 中查找 name 对应的 schema，校验后返回 (ok, detail)。
    无 schema 或 schema 无 properties 时直通（ok=True）。

    Args:
        name: 工具名
        args: 实际传入的参数 dict
        definitions: ToolRegistry._definitions（OpenAI function 格式）

    Returns:
        (True, "") 校验通过
        (False, "[错误] 参数校验失败: ...。期望: ...") 校验失败
    """
    if not isinstance(args, dict):
        return True, ""  # 非标准参数，跳过校验

    # 查找工具定义
    schema = None
    for d in definitions:
        fn = d.get("function", {})
        if fn.get("name") == name:
            schema = fn.get("parameters", {})
            break

    if not schema or not isinstance(schema, dict):
        return True, ""  # 无 schema，直通

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    if not properties:
        return True, ""  # 无参数约束，直通

    # 1. required 字段存在性检查
    missing = [r for r in required if r not in args or args.get(r) is None]
    if missing:
        hint_parts = [f"{p}({properties[p].get('type', 'any')})" for p in required if p in properties]
        schema_hint = ", ".join(hint_parts) if hint_parts else ", ".join(required)
        return False, (f"[错误] 参数校验失败: 缺少必需参数 {missing}。期望: {schema_hint}。请补充缺失参数后重试。")

    # 2. 基本类型检查（只检查提供的参数）
    for pname, pval in args.items():
        if pname not in properties or pval is None:
            continue
        expected_type = properties[pname].get("type", "")
        if not expected_type:
            continue
        actual_type = _PY_TYPE_MAP.get(type(pval), "")
        # 宽松匹配：integer 可接受 bool 的反向不行，但 number 接受 int/float
        type_ok = False
        if expected_type == "string":
            type_ok = isinstance(pval, str)
        elif expected_type == "integer":
            type_ok = isinstance(pval, int) and not isinstance(pval, bool)
        elif expected_type == "number":
            type_ok = isinstance(pval, (int, float)) and not isinstance(pval, bool)
        elif expected_type == "boolean":
            type_ok = isinstance(pval, bool)
        elif expected_type == "array":
            type_ok = isinstance(pval, (list, tuple))
        elif expected_type == "object":
            type_ok = isinstance(pval, dict)

        if not type_ok:
            hint_parts = [f"{p}({properties[p].get('type', 'any')})" for p in required if p in properties]
            schema_hint = ", ".join(hint_parts) if hint_parts else ""
            return False, (
                f"[错误] 参数校验失败: 参数 '{pname}' 类型应为 {expected_type}，"
                f"实际为 {actual_type or type(pval).__name__}。"
                f"期望: {schema_hint}。请修正参数类型后重试。"
            )

    return True, ""


def _levenshtein(a: str, b: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离（纯计算，无外部依赖）。"""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _suggest_similar_tool(name: str, definitions: list[dict], top_n: int = 2) -> str:
    """基于编辑距离 + 前缀匹配推荐相似工具名（#4）。

    Args:
        name: 未知工具名（用户输入或模型生成）
        definitions: ToolRegistry._definitions
        top_n: 返回前 N 个建议

    Returns:
        形如 "read_file / edit_file" 的字符串；无候选时返回 ""。
    """
    if not name or not definitions:
        return ""

    candidates: list[tuple[str, float]] = []
    name_lower = name.lower()
    for d in definitions:
        fn = d.get("function", {})
        tool_name = fn.get("name", "")
        if not tool_name:
            continue
        # 编辑距离（归一化到 0-1，越小越相似）
        dist = _levenshtein(name_lower, tool_name.lower())
        max_len = max(len(name), len(tool_name), 1)
        similarity = 1.0 - (dist / max_len)
        # 前缀匹配加分
        if tool_name.lower().startswith(name_lower[:3]) or name_lower.startswith(tool_name.lower()[:3]):
            similarity += 0.2
        # 包含关系加分
        if name_lower in tool_name.lower() or tool_name.lower() in name_lower:
            similarity += 0.15
        # 只保留相似度 > 0.4 的候选
        if similarity > 0.4:
            candidates.append((tool_name, similarity))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return " / ".join(c[0] for c in candidates[:top_n])


# ── 工具注册表 ──

# ── 动态工具过滤：默认只发核心工具（~25个），按需扩展 ──
# 每次请求的工具定义约 14K tokens → 核心模式 ~2.5K tokens，大幅降低 TTFT。

CORE_TOOL_NAMES: set[str] = {
    # Web
    "web_search",
    "web_fetch",
    "http_request",
    # File I/O
    "read_file",
    "write_file",
    "search_files",
    "glob_files",
    "list_files",
    # Code basics
    "code_analyze",
    "code_review",
    "run_python",
    "run_bash",
    "run_format",
    "run_lint",
    # System introspection
    "env_check",
    "think_deep",
    "estimate_tokens",
    "tool_search",
    # Task management
    "task_launch",
    "task_list",
    # Core media
    "generate_image",
    "generate_video",
    # Document
    "create_markdown",
    "create_html",
    "download_file",
    "view_image",
    # Debug
    "debug_inspect",
    "inspect_last_error",
}

# 扩展分类 → 工具名集合（注意：与上面的 TOOL_CATEGORIES 展示分类不同，这里是动态展开用）
TOOL_EXPANSION_CATEGORIES: dict[str, set[str]] = {
    "git": {
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
        "git_push",
        "git_pull",
        "git_stash",
        "git_tag",
        "git_worktree",
        "git_add_commit",
        "git_conflict_check",
        "git_pr_create",
        "git_pr_merge",
        "github_search",
        "github_repo_view",
        "github_repo_list",
        "github_browse",
        "github_readme",
        "github_release",
        "github_issue",
        "github_pr",
        "github_api",
        "github_write_file",
    },
    "comfyui": {
        "comfyui_status",
        "comfyui_list_models",
        "comfyui_submit_workflow",
        "comfyui_get_result",
        "comfyui_preview_workflow",
        "comfyui_clear_queue",
        "comfyui_get_node_info",
        "comfyui_build_custom_workflow",
        "comfyui_create_custom_node",
        "comfyui_lora_prepare",
        "comfyui_lora_generate_config",
        "comfyui_lora_check_status",
    },
    "lsp": {
        "lsp_goto_definition",
        "lsp_hover",
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_completion",
        "lsp_rename",
    },
    "notebook": {
        "notebook_open",
        "notebook_edit_cell",
        "notebook_add_cell",
        "notebook_run_cell",
        "notebook_save",
    },
    "code_extended": {
        "edit_file",
        "patch_file",
        "patch_undo",
        "safe_rewrite_file",
        "run_test",
        "pip_install",
        "self_heal",
        "security_review",
    },
    "browser": {"browser_screenshot", "pw_navigate", "pw_screenshot"},
    "task_extended": {
        "todo_add",
        "todo_list",
        "todo_update",
        "todo_delete",
        "todo_dep",
        "todo_blocked",
        "todo_stats",
        "create_goal",
        "get_goal",
        "set_goal_budget",
        "update_goal",
        "goal_evaluate",
        "execute_plan",
        "enter_plan_mode",
        "exit_plan_mode",
        "plan_status",
        "update_plan",
    },
    "trm": {"trm_route", "trm_growth", "trm_tune", "trm_catalog"},
    "knowledge_graph": {
        "find_symbol",
        "search_symbols",
        "find_references",
        "graph_neighbors",
        "graph_ancestors",
        "graph_descendants",
    },
    "media_extended": {"imagegen", "text_to_speech", "transcribe_audio", "desktop_screenshot"},
    "mcp": {
        "mcp_connect",
        "mcp_call",
        "mcp_list_servers",
        "mcp_list_tools",
        "mcp_call_tool",
        "mcp_read_resource",
    },
    "agent": {"agent_swarm", "multi_agent", "skill_search"},
    "deploy": {"deploy_vercel"},
    "misc": {
        "db_query",
        "js_eval",
        "create_pdf",
        "request_user_input",
        "count_lines",
        "tree_dir",
    },
}

# 关键词 → 分类映射（用户输入匹配后自动展开对应分类）
CATEGORY_HINTS: dict[str, str] = {}
for _cat, _kws in {
    "git": [
        "git",
        "commit",
        "push",
        "pull",
        "branch",
        "merge",
        "pr",
        "pull request",
        "github",
        "repo",
        "仓库",
        "提交",
        "推送",
    ],
    "comfyui": ["comfyui", "stable diffusion", "lora", "workflow", "node"],
    "lsp": ["lsp", "goto definition", "hover", "diagnostic", "代码跳转", "重命名"],
    "notebook": ["notebook", "jupyter", "ipynb", "cell", "单元格"],
    "code_extended": ["edit", "patch", "rewrite", "refactor", "改代码", "修改", "测试", "test", "install", "安装"],
    "browser": ["browser", "screenshot", "截图", "navigate", "网页"],
    "task_extended": ["goal", "todo", "plan mode", "目标", "计划", "任务"],
    "deploy": ["deploy", "vercel", "部署"],
    "media_extended": ["speech", "语音", "transcribe", "转写", "tts", "音频"],
    "mcp": ["mcp"],
    "agent": ["agent", "swarm", "多智能体", "并行"],
}.items():
    for _kw in _kws:
        CATEGORY_HINTS[_kw] = _cat


def _resolve_tool_names(user_input: str, *, full: bool = False) -> set[str]:
    """根据用户输入决定发送哪些工具名。

    - full=True：返回全部工具
    - 否则：核心工具 + 关键词匹配到的扩展分类
    """
    if full:
        return set()  # 空集 = 发全部（由调用方处理）

    names = set(CORE_TOOL_NAMES)
    if user_input:
        text_lower = user_input.lower()
        for keyword, category in CATEGORY_HINTS.items():
            if keyword in text_lower:
                names.update(TOOL_EXPANSION_CATEGORIES.get(category, set()))
    return names


class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []  # OpenAI function 格式
        self._executors: dict[str, Callable[..., str]] = {}  # name → 执行函数
        self._tool_modules: dict[str, str] = {}  # name → 模块路径（分类用）
        self.model_router = None  # Optional ModelRouter for sub-agent dispatch

    # ── 加载 ──
    def load(
        self,
        pipeline: bool = False,
        comfyui: bool = False,
        browser: bool = False,
        notebook: bool = False,
        audio: bool = False,
        mcp: bool = False,
        agnes: bool = False,
        comfyui_pipeline: bool = False,
        showrunner: bool = False,
    ) -> int:
        """从 tools.json 加载工具，返回已加载数量

        Args:
            pipeline: 是否加载一键流视频管道工具（Showrunner 模式）
            comfyui: 是否加载 ComfyUI 桥接工具（ComfyUI Bridge 模式）
            browser: 是否加载 Browser Companion 网页生成工具
            notebook: 是否加载 Notebook (.ipynb) 工具
            agnes: 是否加载 Agnes 多模态生成工具
            comfyui_pipeline: 是否加载 ComfyUI 高级工作流工具
            showrunner: 是否加载 Showrunner 专业流水线工具
            audio: 是否加载音频工具（TTS/BGM/SFX/混音）
            mcp: 是否加载 MCP Client 桥接工具（四象融合：调 claude/codex/codebuddy）
            多个可同时为 True（协作模式）
        """
        self._definitions = list(BUILTIN_TOOLS)
        self._executors.clear()
        self._tool_modules.clear()
        # builtin 工具的模块标记
        for d in self._definitions:
            self._tool_modules[d["function"]["name"]] = _BUILTIN_MODULE

        # ── 管道工具 ──
        if pipeline:
            self._definitions.extend(PIPELINE_TOOL_DEFS)
            from core.pipeline_tools import EXECUTOR_MAP as PIPELINE_EXECUTORS

            for name, executor in PIPELINE_EXECUTORS.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.pipeline_tools"

        # ── ComfyUI 桥接工具 ──
        if comfyui:
            self._definitions.extend(COMFYUI_TOOL_DEFS)
            from core.comfyui_tools import COMFYUI_EXECUTOR_MAP

            for name, executor in COMFYUI_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.comfyui_tools"

        # ── Agnes 多模态生成（文生图/图生图/文生视频/图生视频）──
        if agnes:
            from core.agnes_multimodal import AGNES_EXECUTOR_MAP, AGNES_TOOL_DEFS

            self._definitions.extend(AGNES_TOOL_DEFS)
            for name, executor in AGNES_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.agnes_multimodal"

        # ── ComfyUI 高级工作流（AI建工作流/调参/练LoRA）──
        if comfyui_pipeline:
            from core.comfyui_pipeline import (
                COMFYUI_PIPELINE_EXECUTOR_MAP,
                COMFYUI_PIPELINE_TOOL_DEFS,
            )

            self._definitions.extend(COMFYUI_PIPELINE_TOOL_DEFS)
            for name, executor in COMFYUI_PIPELINE_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.comfyui_pipeline"

        # ── Showrunner 专业流水线（文案→图片→视频→影片）──
        if showrunner:
            from core.showrunner_pipeline import (
                SHOWRUNNER_EXECUTOR_MAP,
                SHOWRUNNER_TOOL_DEFS,
            )

            self._definitions.extend(SHOWRUNNER_TOOL_DEFS)
            for name, executor in SHOWRUNNER_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.showrunner_pipeline"

        # ── Browser Companion 网页生成工具 ──
        if browser:
            from core.browser_tools import BROWSER_EXECUTOR_MAP, BROWSER_TOOL_DEFS

            self._definitions.extend(BROWSER_TOOL_DEFS)
            for name, executor in BROWSER_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.browser_tools"

        # ── Notebook (.ipynb) 工具 ──
        if notebook:
            from core.notebook import NOTEBOOK_EXECUTOR_MAP, NOTEBOOK_TOOL_DEFS

            self._definitions.extend(NOTEBOOK_TOOL_DEFS)
            for name, executor in NOTEBOOK_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.notebook"

        # ── 音频工具（TTS/BGM/SFX/混音）──
        if audio:
            from core.audio_tools import AUDIO_EXECUTOR_MAP, AUDIO_TOOL_DEFS

            self._definitions.extend(AUDIO_TOOL_DEFS)
            for name, executor in AUDIO_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.audio_tools"

        # ── LSP 代码智能工具（常驻加载）──
        # goto_definition / hover / diagnostics / find_references / completion / rename
        from core.lsp import LSP_EXECUTOR_MAP, LSP_TOOL_DEFS

        self._definitions.extend(LSP_TOOL_DEFS)
        for name, executor in LSP_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.lsp"

        # ── Git 工作流工具 (P-2: 常驻加载, 不需要 toggle) ──
        # branch / push / pull / pr / stash / tag / worktree / conflict_check
        # 与 tools.json 中 git_status/diff/log/add_commit 互补,不重名。
        # 注入后 _HIGH_RISK_TOOLS 确认门对 git_push/pr_create/pr_merge/tag 真正生效。
        from core.git_tools import GIT_WORKFLOW_EXECUTOR_MAP
        from core.git_tools import GIT_WORKFLOW_TOOL_DEFS as _GIT_WF_DEFS

        self._definitions.extend(_GIT_WF_DEFS)
        for name, executor in GIT_WORKFLOW_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.git_tools"

        # ── 后台任务管理工具（常驻加载）──
        # task_launch / task_list / task_output / task_stop
        # 移植自 Kimi Code CLI，填补 run_in_background 功能空白
        from core.background import BACKGROUND_EXECUTOR_MAP, BACKGROUND_TOOL_DEFS

        self._definitions.extend(BACKGROUND_TOOL_DEFS)
        for name, executor in BACKGROUND_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.background"

        # ── 目标评估器工具（常驻加载）──
        # goal_evaluate: 评估目标完成度，给出 pass/fail/needs_fix 裁决
        from core.goal_evaluator import GOAL_EVALUATE_TOOL_DEF, _exec_goal_evaluate

        self._definitions.append(GOAL_EVALUATE_TOOL_DEF)
        self._executors["goal_evaluate"] = _exec_goal_evaluate
        self._tool_modules["goal_evaluate"] = "core.goal_evaluator"

        # ── 规划模式工具（常驻加载）──
        # enter_plan_mode / exit_plan_mode / plan_status
        from core.plan_mode import PLAN_MODE_EXECUTOR_MAP, PLAN_MODE_TOOL_DEFS

        self._definitions.extend(PLAN_MODE_TOOL_DEFS)
        for name, executor in PLAN_MODE_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Quest Engine (方法论第5章) ──
        from core.quest_engine import QUEST_EXECUTOR_MAP, QUEST_TOOL_DEFS

        self._definitions.extend(QUEST_TOOL_DEFS)
        for name, executor in QUEST_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── WorkBuddy 办公Agent (方法论第19章) ──
        from core.workbuddy import WORKBUDDY_EXECUTOR_MAP, WORKBUDDY_TOOL_DEFS

        self._definitions.extend(WORKBUDDY_TOOL_DEFS)
        for name, executor in WORKBUDDY_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Repo Wiki 知识库 (方法论第6章) ──
        from core.repo_wiki import WIKI_EXECUTOR_MAP, WIKI_TOOL_DEFS

        self._definitions.extend(WIKI_TOOL_DEFS)
        for name, executor in WIKI_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── ADR 架构决策记录 (方法论第8章) ──
        from core.adr_engine import ADR_EXECUTOR_MAP, ADR_TOOL_DEFS

        self._definitions.extend(ADR_TOOL_DEFS)
        for name, executor in ADR_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── TDD 工作流 (方法论第10章) ──
        from core.tdd_workflow import TDD_EXECUTOR_MAP, TDD_TOOL_DEFS

        self._definitions.extend(TDD_TOOL_DEFS)
        for name, executor in TDD_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Retro 复盘 (方法论第9章) ──
        from core.retro_engine import RETRO_EXECUTOR_MAP, RETRO_TOOL_DEFS

        self._definitions.extend(RETRO_TOOL_DEFS)
        for name, executor in RETRO_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.plan_mode"

        # ── Agent Swarm 工具（常驻加载）──
        from core.multi_agent import AGENT_SWARM_TOOL_DEF, _exec_agent_swarm

        self._definitions.append(AGENT_SWARM_TOOL_DEF)
        self._executors["agent_swarm"] = _exec_agent_swarm
        self._tool_modules["agent_swarm"] = "core.multi_agent"

        # ── 代码审查工具（常驻加载）──
        # code_review / security_review — 借鉴 Copilot CLI /review + /security-review
        from core.code_review import CODE_REVIEW_EXECUTOR_MAP, CODE_REVIEW_TOOL_DEFS

        self._definitions.extend(CODE_REVIEW_TOOL_DEFS)
        for name, executor in CODE_REVIEW_EXECUTOR_MAP.items():
            self._executors[name] = executor
        # ── CI/CD Pipeline (方法论第10章) ──
        from core.ci_pipeline import PIPELINE_EXECUTOR_MAP, PIPELINE_TOOL_DEFS
        self._definitions.extend(PIPELINE_TOOL_DEFS)
        for name, executor in PIPELINE_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Artifact Pipeline (方法论第13章) ──
        from core.artifact_pipeline import ARTIFACT_EXECUTOR_MAP, ARTIFACT_TOOL_DEFS
        self._definitions.extend(ARTIFACT_TOOL_DEFS)
        for name, executor in ARTIFACT_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Rollback/Gray-release (方法论第14章) ──
        from core.rollback_engine import RELEASE_EXECUTOR_MAP, RELEASE_TOOL_DEFS
        self._definitions.extend(RELEASE_TOOL_DEFS)
        for name, executor in RELEASE_EXECUTOR_MAP.items():
            self._executors[name] = executor

            self._tool_modules[name] = "core.code_review"

        # ── 会话任务追踪工具（常驻加载）──
        # todo_add / todo_list / todo_update / todo_delete / todo_dep / todo_blocked / todo_stats
        # 借鉴 Copilot CLI SQL todos + todo_deps 表设计
        from core.session_tracker import SESSION_TRACKER_EXECUTOR_MAP, SESSION_TRACKER_TOOL_DEFS

        self._definitions.extend(SESSION_TRACKER_TOOL_DEFS)
        for name, executor in SESSION_TRACKER_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.session_tracker"

        # ── 代码格式化 & 静态检查工具（常驻加载）──
        # run_format: ruff format + isort (Python) / prettier (JS/TS)
        # run_lint: ruff check (Python) / eslint (JS/TS)
        from core.format_tools import FORMAT_EXECUTOR_MAP, FORMAT_TOOL_DEFS

        self._definitions.extend(FORMAT_TOOL_DEFS)
        for name, executor in FORMAT_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.format_tools"

        # ── 运行时检查工具（常驻加载）──
        # debug_inspect: run test/script, capture traceback + frame locals on failure
        from core.runtime_inspect import INSPECT_EXECUTOR_MAP, INSPECT_TOOL_DEFS

        self._definitions.extend(INSPECT_TOOL_DEFS)
        for name, executor in INSPECT_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.runtime_inspect"

        # ── 自愈工具（常驻加载）──
        # self_heal: audit + auto-fix the entire codebase

        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "self_heal",
                    "description": "Audit and auto-fix the CRUX codebase. Scans for: silent exceptions, syntax errors, config drift, import failures, test failures. Use --fix to auto-patch fixable issues.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fix": {
                                "type": "boolean",
                                "description": "Auto-fix what can be safely fixed (default: audit only)",
                            },
                            "quick": {
                                "type": "boolean",
                                "description": "Skip slow scans (imports, tests) for fast feedback",
                            },
                        },
                        "required": [],
                    },
                },
            }
        )
        self._executors["self_heal"] = lambda **kw: _exec_self_heal(
            fix=bool(kw.get("fix", False)),
            quick=bool(kw.get("quick", False)),
        )
        self._tool_modules["self_heal"] = "core.self_heal"

        # ── MCP Client 桥接工具（四象融合）──
        # 注入 mcp_list_servers / mcp_list_tools / mcp_call_tool / mcp_read_resource，
        # 让 LLM 能通过 MCP 协议调 claude/codex/codebuddy 的工具。
        # 远程 server 通过 `crux mcp add <name> -- <command>` 配置，
        # executor 自带 auto-connect（首次调用时自动启动子进程握手）。
        if mcp:
            from core.mcp_client import MCP_EXECUTOR_MAP, MCP_TOOL_DEFS

            self._definitions.extend(MCP_TOOL_DEFS)
            for name, executor in MCP_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.mcp_client"

        if not self._config_path.exists():
            return len(self._definitions)

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return len(self._definitions)

        for tool_cfg in config.get("tools", []):
            name = tool_cfg.get("name", "")

            # P-4 去重：如果同名工具已由 toggle/内置加载（如 comfyui_*），跳过
            # 避免工具定义中出现重复条目导致 LLM 看到重复工具。
            if name in self._executors:
                continue

            desc = tool_cfg.get("description", name)
            params = tool_cfg.get("parameters", {})
            properties = {}
            required = []

            # 构建 OpenAI function 格式的参数 schema
            for pname, pinfo in params.items():
                properties[pname] = {
                    "type": pinfo.get("type", "string"),
                    "description": pinfo.get("description", pname),
                }
                if pinfo.get("required", False):
                    required.append(pname)

            func_def = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            self._definitions.append(func_def)

            # 注册执行器 + 记录模块路径（分类用）
            self._executors[name] = self._make_executor(name, tool_cfg)
            self._tool_modules[name] = tool_cfg.get("function", "").rsplit(".", 1)[0]

        # ── Fast Scanner ──
        try:
            from core.fast_scanner import SCANNER_EXECUTOR_MAP, SCANNER_TOOL_DEFS
            self._definitions.extend(SCANNER_TOOL_DEFS)
            for _n, _e in SCANNER_EXECUTOR_MAP.items():
                self._executors[_n] = _e
        except Exception:
            pass

        # ── MCP Health Check ──
        try:
            self._definitions.append({"type": "function", "function": {
                "name": "mcp_health_check",
                "description": "Check MCP connection health and reconnect if dead.",
                "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}}}
            }})
            from core.mcp_client import get_mcp_client
            def _hchk(**kw):
                import json
                mc = get_mcp_client()
                if kw.get("server_name"):
                    return json.dumps(mc.health_check(kw["server_name"]))
                return json.dumps(mc.health_check_all())
            self._executors["mcp_health_check"] = _hchk
        except Exception:
            pass

        # 去重
        seen = set()
        self._definitions = [d for d in self._definitions if not (d.get("function", {}).get("name") in seen or seen.add(d.get("function", {}).get("name")))]

        return len(self._definitions)

    # ── 执行器工厂 ──
    def _make_executor(self, name: str, cfg: dict) -> Callable[..., str]:
        """根据类型创建执行函数"""
        t = cfg.get("type", "shell")

        def shell_executor(**kwargs):
            import shlex
            import shutil
            import subprocess as _sp
            import sys

            # ── 提取 shell 控制参数（Copilot CLI 三模式）──
            run_in_background = kwargs.pop("run_in_background", False)
            detach = kwargs.pop("detach", False)
            description = kwargs.pop("description", "")

            safe_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, str):
                    safe_kwargs[k] = shlex.quote(v)
                else:
                    safe_kwargs[k] = v

            raw_cmd = cfg.get("command", "{command}")
            cmd = raw_cmd.format(**safe_kwargs)

            # ── 沙箱验证 ──
            try:
                from core.sandbox import sandbox_restrict

                cmd = sandbox_restrict(cmd)
            except RuntimeError as e:
                return f"[沙箱拒绝] {e}"
            except ImportError:
                pass

            # ── detach 模式：Popen 后台启动，立即返回 pid ──
            if detach:
                if sys.platform == "win32" and not shutil.which("bash"):
                    popen_cmd = cmd
                else:
                    popen_cmd = cmd
                proc = _sp.Popen(
                    popen_cmd,
                    shell=True,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    stdin=_sp.DEVNULL,
                    creationflags=_sp.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
                return f"[detached] pid={proc.pid}" + (f" ({description})" if description else "")

            # ── 超时控制：background 模式放宽超时 ──
            _timeout = cfg.get("timeout", 30)
            if run_in_background:
                _timeout = max(_timeout, 300)  # 后台任务至少 5 分钟

            # ── 跨平台执行 ──
            if sys.platform == "win32" and not shutil.which("bash"):
                r = _sp.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout,
                )
            else:
                r = _sp.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout,
                )
            return r.stdout.strip() or r.stderr.strip() or f"[exit: {r.returncode}]"

        def http_executor(**kwargs):
            import httpx

            url = cfg["url"].format(**kwargs)
            method = cfg.get("method", "GET").upper()
            headers = cfg.get("headers", {})
            timeout = cfg.get("timeout", 30)
            resp = httpx.request(method, url, headers=headers, timeout=timeout)
            return resp.text[:2000]

        def python_executor(**kwargs):
            mod_path, func_name = cfg["function"].rsplit(".", 1)
            # 导入白名单：仅允许 core./engines./pipeline./ui./utils. 下的模块
            _ALLOWED_PREFIXES = ("core.", "engines.", "pipeline.", "ui.", "utils.")
            if not any(mod_path.startswith(p) for p in _ALLOWED_PREFIXES):
                return f"[安全拒绝] 禁止导入外部模块: {mod_path}"
            _BLOCKED_MODULES = {
                "os",
                "subprocess",
                "shutil",
                "ctypes",
                "socket",
                "signal",
                "sys",
                "pty",
                "importlib",
                "inspect",
            }
            if mod_path.split(".")[-1] in _BLOCKED_MODULES:
                return f"[安全拒绝] 禁止导入危险模块: {mod_path}"
            mod = importlib.import_module(mod_path)
            return getattr(mod, func_name)(**kwargs)

        
# ── 注册/注销 ──
    def register(
        self, name: str, description: str, parameters: dict, executor: Callable[..., str], override: bool = False
    ):
        """动态注册一个工具"""
        if name in self._executors and not override:
            return False
        func_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._definitions.append(func_def)
        self._executors[name] = executor

        return True

    def unregister(self, name: str) -> bool:
        """注销工具"""
        self._definitions = [d for d in self._definitions if d.get("function", {}).get("name") != name]
        return self._executors.pop(name, None) is not None

    # ── 查询 ──
    @property
    def definitions(self) -> list[dict]:
        return self._definitions

    def get_filtered_definitions(self, user_input: str = "", *, full: bool = False) -> list[dict]:
        """按需返回工具定义，降低每次请求的 token 开销。

        默认只返回核心工具（~25 个，约 2.5K tokens vs 全量 14K tokens）。
        - full=True 或 user_input 匹配扩展关键词时，额外展开对应分类。
        - 传空 user_input 且 full=False → 仅核心工具。
        """
        names = _resolve_tool_names(user_input, full=full)
        if not names:  # 空集 = 发全部
            return self._definitions
        return [d for d in self._definitions if d["function"]["name"] in names]

    @property
    def tool_names(self) -> list[str]:
        return [d["function"]["name"] for d in self._definitions]

    @property
    def tool_categories(self) -> dict[str, list[str]]:
        """返回 {分类名: [工具名,...]}，按 TOOL_CATEGORIES 顺序归类。

        未匹配任何分类的工具归入「其他」。分类映射见模块级 TOOL_CATEGORIES。
        """
        result: dict[str, list[str]] = {}
        others: list[str] = []
        # 预初始化分类键（保持顺序）
        for cat_name, _, _ in TOOL_CATEGORIES:
            result[cat_name] = []

        for d in self._definitions:
            name = d["function"]["name"]
            mod = self._tool_modules.get(name, "")
            matched = False
            for cat_name, prefixes, explicit in TOOL_CATEGORIES:
                # 显式工具名优先匹配
                if name in explicit:
                    result[cat_name].append(name)
                    matched = True
                    break
                # 前缀匹配（空前缀跳过）
                if prefixes and prefixes != ("",) and any(mod.startswith(p) for p in prefixes):
                    result[cat_name].append(name)
                    matched = True
                    break
            if not matched:
                others.append(name)

        # 过滤空分类 + 追加「其他」
        result = {k: v for k, v in result.items() if v}
        if others:
            result["📦 其他"] = others
        return result

    def has(self, name: str) -> bool:
        return name in self._executors

    def schema(self, name: str) -> dict | None:
        """Return the JSON Schema for a registered tool."""
        for d in self.definitions:
            if d.get("name") == name:
                params = d.get("parameters")
                return {"parameters": params} if params else None
        return None

    # ── 执行 ──
    def execute(self, name: str, args: dict, validate_result: bool = True) -> str:
        """执行工具并返回结果文本（含轻量观测 + 错误自动恢复 #4）

        错误恢复策略（#4 新增）:
        - 未知工具 → TF-IDF 相似工具建议（而非裸错误）
        - 参数校验 → required 缺失/类型不匹配 → 带期望 schema 的错误字符串
        - 执行异常 → ErrorClassifier 分类 + 恢复建议（而非裸 raise）
        """
        try:
            from core.observability import TraceContext
            from core.observability import metrics as _m
        except ImportError:
            _m = None  # observability 不可用时静默降级
            TraceContext = None  # type: ignore[assignment]

        # 调用日志（可选，失败时静默降级）
        try:
            from core.tool_call_log import log_call as _log_call
        except ImportError:
            _log_call = None

        executor = self._executors.get(name)
        if not executor:
            # NEW (#4): 相似工具建议，帮助模型自我修正
            suggestion = _suggest_similar_tool(name, self._definitions)
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_suggestion_given")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "unknown_tool", 0.0, args)
            if suggestion:
                return f"[错误] 未知工具: {name}。你是否想用: {suggestion}？请检查工具名后重试。"
            return f"[错误] 未知工具: {name}。请检查工具名后重试。"

        # NEW (#4): 前置参数校验
        ok, detail = _validate_args(name, args, self._definitions)
        if not ok:
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_arg_validation_failed")
                _m.increment(f"tool_err.{name}")  # 按名分桶
                _m.increment(f"tool_arg_fail.{name}")  # 参数失败单独计数
            if _log_call:
                _log_call(name, "arg_validation_failed", 0.0, args)
            return detail

        try:
            ctx = TraceContext("registry_execute", tool_name=name) if _m else _noop_cm()  # type: ignore[operator]
            with ctx as span:
                result = executor(**args)
                elapsed_ms = span.duration_ms() if span is not None else 0.0
                if _m and span is not None:
                    span.set_attribute("result_chars", len(str(result)))
                    _m.increment("tool_executions")
                    _m.timing("tool_execute_ms", elapsed_ms)
                    _m.increment(f"tool_exec.{name}")  # 按名分桶
                    _m.timing(f"tool_ms.{name}", elapsed_ms)  # 按名耗时
            if _log_call:
                _log_call(name, "ok", elapsed_ms, args)

            # NEW: Qoder-style Semantic Return Validation
            result_str = str(result)
            if validate_result:
                result_str = self._validate_result(name, result_str, args)

            return result_str
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            # NEW (#4): 错误分类 + 恢复建议（让模型自我修正，而非裸 raise）
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            try:
                from core.resilience import ErrorClassifier

                etype = ErrorClassifier.classify(e)
                hint = ErrorClassifier.get_recovery_hint(e)
                return f"[错误 | {etype.value}] {e}。恢复建议: {hint}。请检查参数或方法后重试。"
            except ImportError:
                # resilience 不可用：退回原行为（raise）
                raise
        except Exception as e:
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            return f"[错误] 工具 '{name}' 执行失败: {e}"

    # ── #2 Qoder-style: Semantic Return Validator ──
    @staticmethod
    def _validate_result(tool_name: str, result: str, args: dict) -> str:
        """Lightweight semantic validation of tool results.

        Qoder 理念：不只校验输入参数，还要嗅探结果质量——
        空结果、误判成功、格式异常都应标记，让 LLM 自行修正。

        Returns annotated result string with optional quality tags.
        """
        annotations: list[str] = []

        # 1. 空结果检测（写了文件/搜索了代码却返回空，大概率有问题）
        empty_sensitive_tools = {
            "read_file",
            "search_files",
            "glob_files",
            "find_symbol",
            "search_symbols",
            "find_references",
            "graph_neighbors",
            "graph_ancestors",
            "graph_descendants",
            "code_analyze",
            "web_search",
            "web_fetch",
            "github_search",
            "github_browse",
            "github_readme",
            "list_files",
            "tree_dir",
            "skill_search",
            "env_check",
            "run_test",
        }
        if tool_name in empty_sensitive_tools and (not result or not result.strip()):
            annotations.append("[语义警告] 结果为空——可能工具未找到目标，请检查参数或尝试其他工具")

        # 2. 读文件但内容是截断标记（说明读取范围可能不对）
        if tool_name == "read_file" and len(result) < 50 and result.strip():
            annotations.append("[语义提示] 返回内容很短，可能需要调整 offset/limit")

        # 3. 搜索返回 "no matches" / "not found" 模式
        if tool_name in ("search_files", "find_symbol", "search_symbols", "find_references") and (
            "no matches" in result.lower() or "not found" in result.lower()
        ):
            annotations.append("[语义提示] 未匹配到结果，建议放宽搜索条件或更换关键词")

        # 4. 编辑/写入操作返回空（正常：write_file/edit_file 成功时不返回值）
        if (
            tool_name
            in ("write_file", "edit_file", "safe_rewrite_file", "patch_file", "git_add_commit", "github_write_file")
            and not result.strip()
        ):
            # 这些工具成功时通常无输出，这是预期的
            return result  # 不加标记

        if annotations:
            sep = "\n\n" if "\n" in result else " | "
            return result + sep + " | ".join(annotations)

        return result


# ── 全局单例（线程安全双重检查锁） ──
_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def _exec_self_heal(fix: bool = False, quick: bool = False) -> str:
    """Execute self_heal tool — audit + optionally fix the codebase."""
    from core.self_heal import SelfHealer

    healer = SelfHealer()
    if quick:
        healer.scan_syntax()
        healer.scan_config_drift()
    else:
        healer.run_all_scans()
    if fix:
        healer.fix_silent_exceptions()
    return healer.report()


def get_registry(config_path: Path | None = None) -> ToolRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ToolRegistry(config_path)
                _registry.load(mcp=True)
    return _registry


def reload_registry():
    global _registry
    with _registry_lock:
        _registry = None
    return get_registry()
