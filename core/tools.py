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
import subprocess
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


# ── 管道工具标志：由 ChatSession 在加载 showrunner 技能后设置为 True ──
_pipeline_tools_enabled = False


__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "BUILTIN_TOOLS",
    "COMFYUI_TOOL_DEFS",
    "PIPELINE_TOOL_DEFS",
    "TOOLS_CONFIG",
    "ToolRegistry",
    "disable_pipeline_tools",
    "enable_pipeline_tools",
    "get_registry",
    "reload_registry",
]


def enable_pipeline_tools():
    """启用一键流视频管道工具（showrunner 技能加载时调用）"""
    global _pipeline_tools_enabled
    _pipeline_tools_enabled = True


def disable_pipeline_tools():
    """禁用管道工具"""
    global _pipeline_tools_enabled
    _pipeline_tools_enabled = False


# ── 内置工具定义（生图/生视频，从 chat.py 移出）──

BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "根据文字描述生成图片。用于生成资产图（角色/场景/道具/载具）或关键帧融合图。可传入参考图片做图生图编辑。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片内容描述（需包含风格/光影/构图/负面约束）"},
                    "image_url": {"type": "string", "description": "可选，参考图片URL或路径，用于图生图/资产融合"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": "根据文字描述或关键帧图生成视频。支持文生视频和图生视频两种模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "视频内容/运动描述"},
                    "image_url": {"type": "string", "description": "可选，关键帧图片URL或路径，传入时走图生视频"},
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

AGENT_SYSTEM_PROMPT = """你是 CRUX 智能体主脑。你可以调用多种工具来完成任务：

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
    ("🔍 代码智能", ("core.code_intel", "core.rag"), frozenset()),
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


class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []  # OpenAI function 格式
        self._executors: dict[str, Callable[..., str]] = {}  # name → 执行函数
        self._tool_modules: dict[str, str] = {}  # name → 模块路径（分类用）

    # ── 加载 ──
    def load(
        self,
        pipeline: bool = False,
        comfyui: bool = False,
        browser: bool = False,
        notebook: bool = False,
        audio: bool = False,
        mcp: bool = False,
    ) -> int:
        """从 tools.json 加载工具，返回已加载数量

        Args:
            pipeline: 是否加载一键流视频管道工具（Showrunner 模式）
            comfyui: 是否加载 ComfyUI 桥接工具（ComfyUI Bridge 模式）
            browser: 是否加载 Browser Companion 网页生成工具
            notebook: 是否加载 Notebook (.ipynb) 工具
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
                    full_cmd = f"chcp 65001 >nul && {cmd}"
                    popen_cmd = full_cmd
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
                full_cmd = f"chcp 65001 >nul && {cmd}"
                r = _sp.run(
                    full_cmd,
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

        return {"shell": shell_executor, "http": http_executor, "python": python_executor}[t]

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

    # ── 执行 ──
    def execute(self, name: str, args: dict) -> str:
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
            return str(result)
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
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            return f"[错误] 工具 '{name}' 执行失败: {e}"


# ── 全局单例（线程安全双重检查锁） ──
_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


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
