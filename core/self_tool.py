"""Self-tool creation system.

Allows the AI agent to dynamically create, list, and delete custom tools
during conversation. Created tools are persisted to disk and dynamically
imported + registered into the ToolRegistry.

Structure:
    core/self_tool.py   <- this file
    output/custom_tools/<name>.py  <- generated tool files
"""

import contextlib
import importlib
import json
import re
import sys
import textwrap
import traceback

from core.config import OUTPUT_DIR

__all__ = [
    "CUSTOM_TOOLS_DIR",
    "SELF_TOOL_EXECUTOR_MAP",
    "SELF_TOOL_TOOL_DEFS",
    "ToolBuilder",
    "get_builder",
]

# Directory where custom tool .py files are saved
CUSTOM_TOOLS_DIR = OUTPUT_DIR / "custom_tools"
CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# Valid tool name pattern: alphanumeric + underscore, must start with letter/underscore
_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class ToolBuilder:
    """Builds, persists, and registers custom tools at runtime."""

    def __init__(self, registry) -> None:
        """Initialize with a ToolRegistry instance (from core.tools)."""
        self.registry = registry

    # ------------------------------------------------------------------
    # create_tool
    # ------------------------------------------------------------------

    def create_tool(self, name: str, description: str, parameters: dict, code: str, language: str = "python") -> dict:
        """Create a new custom tool.

        Steps:
          1. Validate the name (alphanumeric + underscore, no conflict).
          2. For Python: compile-check the code for syntax errors.
          3. Save the tool code to OUTPUT_DIR / "custom_tools" / f"{name}.py".
          4. The code must contain a function with the same name as the tool
             that accepts **kwargs.
          5. Dynamically import the module and register the function.
          6. Create an OpenAI function definition and register in ToolRegistry.

        Returns:
            {"success": bool, "tool_name": str, "error": str (if failed)}
        """
        # ── 1. Validate name ──
        if not name or not _NAME_RE.match(name):
            return {
                "success": False,
                "tool_name": name,
                "error": f"Invalid tool name '{name}'. Must be alphanumeric + underscore, "
                f"starting with a letter or underscore.",
            }

        if name in self.registry.tool_names:
            return {
                "success": False,
                "tool_name": name,
                "error": f"Tool '{name}' already exists in the registry.",
            }

        # Only Python is supported for now
        if language != "python":
            return {
                "success": False,
                "tool_name": name,
                "error": f"Unsupported language '{language}'. Only 'python' is supported.",
            }

        # ── 2. Parse parameters (may arrive as JSON string) ──
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "tool_name": name,
                    "error": f"Invalid parameters JSON: {e}",
                }

        if not isinstance(parameters, dict):
            return {
                "success": False,
                "tool_name": name,
                "error": "Parameters must be a JSON schema object.",
            }

        # ── 3. Build the source file ──
        indented_code = textwrap.indent(code, "    ")
        source = f"# Auto-generated custom tool: {name}\n# {description}\ndef {name}(**kwargs):\n{indented_code}\n"

        # ── 4. Compile-check before saving ──
        try:
            compile(source, name, "exec")
        except SyntaxError as e:
            return {
                "success": False,
                "tool_name": name,
                "error": f"Syntax error in tool code: {e}",
            }

        # ── 5. Write to disk ──
        tool_path = CUSTOM_TOOLS_DIR / f"{name}.py"
        try:
            tool_path.write_text(source, encoding="utf-8")
        except OSError as e:
            return {
                "success": False,
                "tool_name": name,
                "error": f"Failed to write tool file: {e}",
            }

        # ── 6. Dynamically import and register ──
        try:
            # Ensure the custom_tools directory is importable
            if str(CUSTOM_TOOLS_DIR.parent) not in sys.path:
                sys.path.insert(0, str(CUSTOM_TOOLS_DIR.parent))

            # Use a unique module name to avoid collisions
            module_name = f"custom_tools.{name}"

            # Remove any previously cached module of the same name
            if module_name in sys.modules:
                del sys.modules[module_name]

            module = importlib.import_module(module_name)
            importlib.reload(module)  # ensure fresh code is loaded

            executor_fn = getattr(module, name, None)
            if executor_fn is None:
                return {
                    "success": False,
                    "tool_name": name,
                    "error": f"Function '{name}' not found in generated module.",
                }

            if not callable(executor_fn):
                return {
                    "success": False,
                    "tool_name": name,
                    "error": f"'{name}' is not callable.",
                }

            # ── 7. Register in ToolRegistry ──
            self.registry.register(
                name,
                description,
                parameters,
                executor_fn,
                override=True,
            )

            return {
                "success": True,
                "tool_name": name,
            }

        except (AttributeError, TypeError):
            tb = traceback.format_exc()
            return {
                "success": False,
                "tool_name": name,
                "error": f"Failed to import/register tool:\n{tb}",
            }

    # ------------------------------------------------------------------
    # list_custom_tools
    # ------------------------------------------------------------------

    def list_custom_tools(self) -> list:
        """List all custom tools saved on disk.

        Returns a list of dicts with name, description, and file path.
        """
        tools = []
        if not CUSTOM_TOOLS_DIR.exists():
            return tools

        for py_file in sorted(CUSTOM_TOOLS_DIR.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            tool_name = py_file.stem
            description = ""
            try:
                content = py_file.read_text(encoding="utf-8")
                # Extract description from the second comment line
                lines = content.splitlines()
                for line in lines:
                    if line.startswith("# ") and not line.startswith("# Auto-generated"):
                        description = line.lstrip("# ").strip()
                        break
            except (OSError, UnicodeDecodeError):
                pass

            tools.append(
                {
                    "name": tool_name,
                    "description": description,
                    "file": str(py_file),
                    "registered": self.registry.has(tool_name),
                }
            )

        return tools

    # ------------------------------------------------------------------
    # delete_tool
    # ------------------------------------------------------------------

    def delete_tool(self, name: str) -> bool:
        """Delete a custom tool file and unregister from ToolRegistry.

        Returns True if the tool was found and deleted, False otherwise.
        """
        # Unregister from registry first
        unregistered = self.registry.unregister(name)

        # Remove the .py file
        tool_path = CUSTOM_TOOLS_DIR / f"{name}.py"
        existed = tool_path.exists()
        if existed:
            with contextlib.suppress(OSError):
                tool_path.unlink()

        # Clean up cached module
        module_name = f"custom_tools.{name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # 成功：registry 注销了 或 文件确实存在并尝试删除了
        return unregistered or existed


# ======================================================================
# Module-level singleton + executor functions for ToolRegistry
# ======================================================================

_builder: ToolBuilder | None = None


def get_builder(registry=None) -> ToolBuilder:
    """Get or create the singleton ToolBuilder instance."""
    global _builder
    if _builder is None or registry is not None:
        if registry is None:
            from core.tools import get_registry

            registry = get_registry()
        _builder = ToolBuilder(registry)
    return _builder


# ── Executor wrappers ──


def _exec_create_tool(**kwargs) -> str:
    """Executor for the create_tool self-tool."""
    builder = get_builder()
    name = kwargs.get("name", "")
    description = kwargs.get("description", "")
    parameters = kwargs.get("parameters", "{}")
    code = kwargs.get("code", "")
    language = kwargs.get("language", "python")
    result = builder.create_tool(name, description, parameters, code, language)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _exec_list_custom_tools(**kwargs) -> str:
    """Executor for the list_custom_tools self-tool."""
    builder = get_builder()
    tools = builder.list_custom_tools()
    return json.dumps(tools, ensure_ascii=False, indent=2)


def _exec_delete_tool(**kwargs) -> str:
    """Executor for the delete_tool self-tool."""
    builder = get_builder()
    name = kwargs.get("name", "")
    deleted = builder.delete_tool(name)
    return json.dumps(
        {"success": deleted, "tool_name": name},
        ensure_ascii=False,
        indent=2,
    )


# ── Tool definitions (OpenAI function format) ──

SELF_TOOL_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": (
                "Create a new custom tool that can be called during conversation. "
                "The tool code must define a function body that uses **kwargs. "
                "The function name must match the tool name. "
                "Parameters must be a JSON schema object describing the tool's arguments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Tool name (alphanumeric + underscore, must start with letter/underscore)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of what the tool does",
                    },
                    "parameters": {
                        "type": "string",
                        "description": (
                            "JSON schema object as a string, describing the tool's parameters. "
                            'Example: {"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}'
                        ),
                    },
                    "code": {
                        "type": "string",
                        "description": (
                            "Python function body (without the def line). "
                            "The code will be placed inside a function named after the tool "
                            "that accepts **kwargs. Access arguments via kwargs.get('param_name')."
                        ),
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (default: python)",
                    },
                },
                "required": ["name", "description", "parameters", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_custom_tools",
            "description": "List all custom tools that have been created and saved on disk.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_tool",
            "description": "Delete a custom tool by name. Removes the file and unregisters from the tool registry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the custom tool to delete",
                    },
                },
                "required": ["name"],
            },
        },
    },
]

# ── Executor map ──

SELF_TOOL_EXECUTOR_MAP = {
    "create_tool": _exec_create_tool,
    "list_custom_tools": _exec_list_custom_tools,
    "delete_tool": _exec_delete_tool,
}
