"""智能体工具注册与执行系统

让 agnes-smart-studio 作为主脑，调用和管理外部工具/脚本/API。
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

import json
import subprocess
import importlib
from collections.abc import Callable
from pathlib import Path


TOOLS_CONFIG = Path(__file__).parent.parent / "tools.json"

# ── 管道工具标志：由 ChatSession 在加载 showrunner 技能后设置为 True ──
_pipeline_tools_enabled = False


__all__ = [
    "AGENT_SYSTEM_PROMPT", "BUILTIN_TOOLS", "COMFYUI_TOOL_DEFS", "PIPELINE_TOOL_DEFS", "TOOLS_CONFIG", "ToolRegistry", "disable_pipeline_tools", "enable_pipeline_tools", "get_registry", "reload_registry",
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
                    "video_path": {
                        "type": "string",
                        "description": "本地视频文件的完整路径"
                    },
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
                    "project_name": {
                        "type": "string",
                        "description": "项目名称"
                    },
                    "manifest": {
                        "type": "object",
                        "description": "项目清单 JSON，包含 phase/stage/assets/shots/script 等字段"
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
                    "file_path": {
                        "type": "string",
                        "description": "要检查的文件路径"
                    },
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
                    "project_name": {
                        "type": "string",
                        "description": "项目名称"
                    },
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
                    "url": {
                        "type": "string",
                        "description": "要获取内容的在线 URL"
                    },
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
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_list_models",
            "description": "列出 ComfyUI 中已安装的模型（大模型/LoRA/VAE/ControlNet）。构建工作流前确认所需模型存在。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_node_info",
            "description": "查询 ComfyUI 已安装节点的类型、输入输出定义。用于自由编排自定义工作流。不传参返回所有节点分类列表，传 node_type 查看具体节点的接线定义。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_type": {"type": "string", "description": "要查询的节点类型名，如 KSampler。不传列出所有类型。"},
                    "category_filter": {"type": "string", "description": "按类别过滤，如 loaders/sampling/conditioning。"}
                },
                "required": []
            }
        }
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
                    "output_node_id": {"type": "integer", "description": "输出节点 ID，不传自动推断。"}
                },
                "required": ["nodes"]
            }
        }
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
                    "node_code": {"type": "string", "description": "完整 Python 节点类代码，含 CATEGORY/RETURN_TYPES/FUNCTION/INPUT_TYPES"}
                },
                "required": ["node_name", "node_code"]
            }
        }
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
                    "wait": {"type": "boolean", "description": "是否等待完成，默认 true"}
                },
                "required": ["workflow_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_get_result",
            "description": "通过 prompt_id 查询 ComfyUI 工作流的执行结果。用于异步提交后查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string", "description": "提交时返回的 prompt_id"}
                },
                "required": ["prompt_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_preview_workflow",
            "description": "将工作流 JSON 发送到 ComfyUI 画布预览，不提交执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {"type": "string", "description": "画布格式的工作流 JSON"}
                },
                "required": ["workflow_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfyui_clear_queue",
            "description": "清空 ComfyUI 当前执行队列，中断正在进行的生成任务。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
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
                    "base_resolution": {"type": "integer", "description": "基础分辨率，SD1.5=512, SDXL=1024"}
                },
                "required": ["dataset_name"]
            }
        }
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
                    "network_alpha": {"type": "integer", "description": "网络alpha，通常dim的一半"}
                },
                "required": ["dataset_name", "base_model"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lora_check_training_status",
            "description": "检查 LoRA 训练输出目录，查看已训练好的 .safetensors 文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "数据集名，不传列出全部"}
                },
                "required": []
            }
        }
    },
]

# ── 通用代理系统提示 ──

AGENT_SYSTEM_PROMPT = """你是 Agnes 智能体主脑。你可以调用多种工具来完成任务：

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


# ── 工具注册表 ──

class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []      # OpenAI function 格式
        self._executors: dict[str, Callable[..., str]] = {}  # name → 执行函数

    # ── 加载 ──
    def load(self, pipeline: bool = False, comfyui: bool = False) -> int:
        """从 tools.json 加载工具，返回已加载数量

        Args:
            pipeline: 是否加载一键流视频管道工具（Showrunner 模式）
            comfyui: 是否加载 ComfyUI 桥接工具（ComfyUI Bridge 模式）
            两者可同时为 True（Showrunner + ComfyUI 协作模式）
        """
        self._definitions = list(BUILTIN_TOOLS)
        self._executors.clear()

        # ── 管道工具 ──
        if pipeline:
            self._definitions.extend(PIPELINE_TOOL_DEFS)
            from core.pipeline_tools import EXECUTOR_MAP as PIPELINE_EXECUTORS
            for name, executor in PIPELINE_EXECUTORS.items():
                self._executors[name] = executor

        # ── ComfyUI 桥接工具 ──
        if comfyui:
            self._definitions.extend(COMFYUI_TOOL_DEFS)
            from core.comfyui_tools import COMFYUI_EXECUTOR_MAP
            for name, executor in COMFYUI_EXECUTOR_MAP.items():
                self._executors[name] = executor

        if not self._config_path.exists():
            return len(self._definitions)

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return len(self._definitions)

        for tool_cfg in config.get("tools", []):
            name = tool_cfg.get("name", "")
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

            # 注册执行器
            self._executors[name] = self._make_executor(name, tool_cfg)

        return len(self._definitions)

    # ── 执行器工厂 ──
    def _make_executor(self, name: str, cfg: dict) -> Callable[..., str]:
        """根据类型创建执行函数"""
        t = cfg.get("type", "shell")

        def shell_executor(**kwargs):
            import shlex
            import shutil
            import sys
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

            # ── 跨平台执行 ──
            if sys.platform == "win32" and not shutil.which("bash"):
                # Windows 无 bash：cmd /c + chcp 65001 强制 UTF-8
                full_cmd = f'chcp 65001 >nul && {cmd}'
                r = subprocess.run(full_cmd, shell=True, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=cfg.get("timeout", 30))
            else:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=cfg.get("timeout", 30))
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
            _BLOCKED_MODULES = {"os", "subprocess", "shutil", "ctypes", "socket",
                                "signal", "sys", "pty", "importlib", "inspect"}
            if mod_path.split(".")[-1] in _BLOCKED_MODULES:
                return f"[安全拒绝] 禁止导入危险模块: {mod_path}"
            mod = importlib.import_module(mod_path)
            return getattr(mod, func_name)(**kwargs)

        return {"shell": shell_executor, "http": http_executor, "python": python_executor}[t]

    # ── 注册/注销 ──
    def register(self, name: str, description: str, parameters: dict,
                 executor: Callable[..., str], override: bool = False):
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
        self._definitions = [d for d in self._definitions
                             if d.get("function", {}).get("name") != name]
        return self._executors.pop(name, None) is not None

    # ── 查询 ──
    @property
    def definitions(self) -> list[dict]:
        return self._definitions

    @property
    def tool_names(self) -> list[str]:
        return [d["function"]["name"] for d in self._definitions]

    def has(self, name: str) -> bool:
        return name in self._executors

    # ── 执行 ──
    def execute(self, name: str, args: dict) -> str:
        """执行工具并返回结果文本"""
        executor = self._executors.get(name)
        if not executor:
            return f"[错误] 未知工具: {name}"
        try:
            result = executor(**args)
            return str(result)
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            return f"[错误] 工具 '{name}' 执行失败: {e}"


# ── 全局单例 ──
_registry: ToolRegistry | None = None


def get_registry(config_path: Path | None = None) -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry(config_path)
        _registry.load()
    return _registry


def reload_registry():
    global _registry
    _registry = None
    return get_registry()
