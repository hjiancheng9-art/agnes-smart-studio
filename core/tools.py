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
"""

import json
import subprocess
import importlib
from pathlib import Path
from typing import Any


TOOLS_CONFIG = Path(__file__).parent.parent / "tools.json"


# ── 内置工具定义（生图/生视频，从 chat.py 移出）──

BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "根据文字描述生成图片。可传入参考图片做图生图编辑。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片内容描述"},
                    "image_url": {"type": "string", "description": "可选，参考图片URL或路径"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": "根据文字描述生成视频。可传入参考图片做图生视频。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "视频内容描述"},
                    "image_url": {"type": "string", "description": "可选，参考图片URL或路径"},
                },
                "required": ["prompt"],
            },
        },
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
5. 普通对话不调用工具"""


# ── 工具注册表 ──

class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []      # OpenAI function 格式
        self._executors: dict[str, callable] = {}  # name → 执行函数

    # ── 加载 ──
    def load(self) -> int:
        """从 tools.json 加载工具，返回已加载数量"""
        self._definitions = list(BUILTIN_TOOLS)
        self._executors.clear()

        if not self._config_path.exists():
            return len(self._definitions)

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return len(self._definitions)

        for tool_cfg in config.get("tools", []):
            name = tool_cfg.get("name", "")
            desc = tool_cfg.get("description", name)
            tool_type = tool_cfg.get("type", "shell")
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
    def _make_executor(self, name: str, cfg: dict) -> callable:
        """根据类型创建执行函数"""
        t = cfg.get("type", "shell")

        def shell_executor(**kwargs):
            cmd = cfg["command"].format(**kwargs)
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=cfg.get("timeout", 30))
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
            mod = importlib.import_module(mod_path)
            return getattr(mod, func_name)(**kwargs)

        return {"shell": shell_executor, "http": http_executor, "python": python_executor}[t]

    # ── 注册/注销 ──
    def register(self, name: str, description: str, parameters: dict,
                 executor: callable, override: bool = False):
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
        except Exception as e:
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
