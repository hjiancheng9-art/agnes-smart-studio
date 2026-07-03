#!/usr/bin/env python3
"""CRUX Vision MCP Server — exposes analyze_image as an MCP tool.

Start: python mcp_vision_server.py
Claude Code config (~/.claude/claude-code.json or .claude/mcp.json):

{
  "mcpServers": {
    "crux-vision": {
      "command": "C:/Users/huangjiancheng/AppData/Local/Programs/Python/Python311/python.exe",
      "args": ["C:/Users/huangjiancheng/agnes-smart-studio/mcp_vision_server.py"]
    }
  }
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _handle_request(request: dict) -> dict | None:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "crux-vision",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "analyze_image",
                        "description": "Analyze an image using CRUX vision models (Zhipu GLM-4V-Flash or Agnes 2.0-flash). Returns a text description.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "image_path": {
                                    "type": "string",
                                    "description": "Local file path or HTTP URL to the image to analyze.",
                                },
                                "question": {
                                    "type": "string",
                                    "description": "What to ask about the image. Default: describe the image.",
                                },
                            },
                            "required": ["image_path"],
                        },
                    }
                ]
            },
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {}) or {}

        if tool_name == "analyze_image":
            from core.vision_tool import analyze_image

            image_path = tool_args.get("image_path", "")
            question = tool_args.get("question", "描述这张图片")

            try:
                result = analyze_image(image_path, question)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result}],
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"分析失败: {e}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    if method == "notifications/initialized":
        return None  # No response for notifications

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    """JSON-RPC over stdio loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = _handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            req_id = request.get("id") if isinstance(request, dict) else None
            err = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
