#!/usr/bin/env python3
"""
trae_to_skill.py — Trae Agent → CRUX Skill 转换器

将 Trae AI IDE 的智能体（Agent）定义转换为 CRUX Studio 的 .skill.json 格式。
支持：
  - 从 JSON 文件导入 trae agent
  - 从 trae 分享链接元数据重建（手动输入字段）
  - 批量转换
  - 反向转换（CRUX skill → trae agent 格式）

用法:
  python tools/trae_to_skill.py import agent.json          # 转换单个
  python tools/trae_to_skill.py import "agent_name" -p ... # 手动创建
  python tools/trae_to_skill.py export skills/xxx.skill.json  # 反向
  python tools/trae_to_skill.py batch ./trae_agents/       # 批量
"""

import json
import os
import re
import sys
from pathlib import Path

# ─── Schema 映射 ───────────────────────────────────────────────
# trae AgentSchema (逆向自 trae.cn JS)
# 字段名可能随版本变化，此为当前已知结构

TRAE_TO_CRUX_MAP = {
    "agentName": "name",
    "agentDescription": "description",
    "agentPrompt": None,  # 特殊处理 → prompt[0].content
    "agentIcon": None,    # 特殊处理 → metadata.icon
    "agentTools": None,   # → requirements 或 metadata.tools
    "mcpTools": None,     # → requirements.mcp_servers
    "builtinTools": None, # → requirements.builtin_tools
    "agentConfig": None,  # → models + configuration
}

CRUX_TO_TRAE_MAP = {v: k for k, v in TRAE_TO_CRUX_MAP.items() if v}


def parse_trae_config(config: dict) -> tuple:
    """从 trae agentConfig 提取 CRUX 配置"""
    model = config.get("model", "deepseek-v4-flash")
    max_tokens = config.get("maxTokens", 4096)
    temperature = config.get("temperature", 0.7)
    return model, {"max_tokens": max_tokens, "temperature": temperature}


def trae_to_skill(trae_data: dict, output_path: str | None = None) -> dict:
    """
    将 trae agent JSON 转换为 CRUX skill.json 格式
    
    参数:
        trae_data: trae agent 字典
        output_path: 可选，写入路径
    
    返回:
        skill_dict: CRUX skill.json 字典
    """
    name = trae_data.get("agentName", trae_data.get("name", "unnamed-agent"))
    description = trae_data.get(
        "agentDescription", trae_data.get("description", "")
    )
    prompt_text = trae_data.get("agentPrompt", trae_data.get("prompt", ""))
    icon = trae_data.get("agentIcon", "")

    # 工具列表
    tools = []
    for t in trae_data.get("agentTools", trae_data.get("tools", [])):
        if isinstance(t, str):
            tools.append(t)
        elif isinstance(t, dict):
            tools.append(t.get("name", t.get("toolName", str(t))))

    mcp_tools = []
    for t in trae_data.get("mcpTools", trae_data.get("mcpServers", [])):
        if isinstance(t, str):
            mcp_tools.append(t)
        elif isinstance(t, dict):
            mcp_tools.append(t.get("name", t.get("serverName", str(t))))

    # 模型配置
    agent_config = trae_data.get("agentConfig", trae_data.get("config", {}))
    model, config_details = parse_trae_config(agent_config)

    # 构建 CRUX skill.json
    skill = {
        "name": _to_skill_name(name),
        "description": _clean_description(description),
        "version": "1.0.0",
        "author": "imported-from-trae",
        "target": "code",
        "models": [model],
        "always_load": False,
        "metadata": {
            "source": "trae.ai",
            "original_name": name,
            "icon": icon,
            "tools": tools,
            "mcp_servers": mcp_tools,
            "config": config_details,
        },
        "prompt": [
            {
                "type": "system",
                "content": prompt_text or _generate_default_prompt(name, description),
            }
        ],
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(skill, f, indent=2, ensure_ascii=False)
        print(f"✓ 写入: {output_path}")

    return skill


def skill_to_trae(skill_path: str, output_path: str | None = None) -> dict:
    """
    反向转换：CRUX skill.json → trae agent 格式
    """
    with open(skill_path, encoding="utf-8") as f:
        skill = json.load(f)

    prompt_content = ""
    for p in skill.get("prompt", []):
        if p.get("type") == "system":
            prompt_content = p.get("content", "")
            break

    metadata = skill.get("metadata", {})
    config = skill.get("metadata", {}).get("config", {})
    model = skill.get("models", ["deepseek-v4-flash"])[0]

    trae_agent = {
        "agentName": metadata.get("original_name", skill.get("name", "")),
        "agentDescription": skill.get("description", ""),
        "agentPrompt": prompt_content,
        "agentIcon": metadata.get("icon", ""),
        "agentTools": metadata.get("tools", []),
        "mcpTools": metadata.get("mcp_servers", []),
        "builtinTools": [],
        "agentConfig": {
            "model": model,
            "maxTokens": config.get("max_tokens", 4096),
            "temperature": config.get("temperature", 0.7),
        },
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trae_agent, f, indent=2, ensure_ascii=False)
        print(f"✓ 写入: {output_path}")

    return trae_agent


def batch_convert(input_dir: str, output_dir: str = "skills") -> list:
    """批量转换 trae agent JSON → skill.json"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = []
    for f in input_path.glob("*.json"):
        with open(f, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                print(f"✗ 跳过无效 JSON: {f.name}")
                continue

        out_file = output_path / f"{_to_skill_name(data.get('agentName', data.get('name', f.stem)))}.skill.json"
        skill = trae_to_skill(data, str(out_file))
        results.append((f.name, str(out_file), "ok"))
        print(f"  ✓ {f.name} → {out_file.name}")

    return results


def _to_skill_name(name: str) -> str:
    """将 agent 名称转为 skill 文件名友好格式"""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '-', name.strip().lower())
    return name or "unnamed-agent"


def _clean_description(desc: str) -> str:
    """清理描述文本"""
    return desc.strip().strip('"').strip("'")


def _generate_default_prompt(name: str, description: str) -> str:
    """当 trae agent 没有 prompt 时，生成一个默认的系统提示词"""
    return f"""You are {name}, an AI agent specialized in: {description}

Follow the user's instructions carefully and precisely.
Use the tools available to you to accomplish the task at hand.
Think step by step when solving complex problems.
"""


def cmd_import(args: list):
    """处理 import 命令"""
    if not args:
        print("用法: python tools/trae_to_skill.py import <agent.json | agent_name>")
        return

    target = args[0]

    if os.path.isfile(target):
        # 从文件导入
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        # 如果是一个列表，取第一个
        if isinstance(data, list):
            data = data[0]
        name = data.get("agentName", data.get("name", Path(target).stem))
        out_path = f"skills/{_to_skill_name(name)}.skill.json"
        trae_to_skill(data, out_path)
        print(f"  → 加载试试: skill_load {_to_skill_name(name)}")
    else:
        # 手动输入字段创建
        name = target
        desc = input("描述: ") if len(args) < 2 else args[1]
        prompt = input("Prompt (多行，空行结束):\n") if len(args) < 3 else args[2]

        data = {
            "agentName": name,
            "agentDescription": desc,
            "agentPrompt": prompt,
            "agentConfig": {"model": "deepseek-v4-flash", "maxTokens": 4096, "temperature": 0.7},
            "agentTools": [],
            "mcpTools": [],
        }
        out_path = f"skills/{_to_skill_name(name)}.skill.json"
        trae_to_skill(data, out_path)
        print(f"  → 加载试试: skill_load {_to_skill_name(name)}")


def cmd_export(args: list):
    """处理 export 命令"""
    if not args:
        print("用法: python tools/trae_to_skill.py export <skill.json> [output.json]")
        return
    skill_path = args[0]
    out_path = args[1] if len(args) > 1 else None
    skill_to_trae(skill_path, out_path)


def cmd_batch(args: list):
    """处理 batch 命令"""
    if not args:
        print("用法: python tools/trae_to_skill.py batch <input_dir> [output_dir]")
        return
    input_dir = args[0]
    output_dir = args[1] if len(args) > 1 else "skills"
    results = batch_convert(input_dir, output_dir)
    print(f"\n批量转换完成: {len(results)} 个")


def cmd_list_tools(_args=None):
    """列出所有已安装的 trae → skill 工具"""
    print("""
Trae → CRUX Skill 转换工具集
────────────────────────────
  import    转换 trae agent JSON → skill.json
  export    反向: skill.json → trae agent JSON
  batch     批量转换整个目录
  schema    显示 trae agent 和 CRUX skill 的字段映射
  help      显示帮助
""")


def cmd_schema(_args=None):
    """显示 schema 映射"""
    print("""
字段映射 (Trae Agent → CRUX Skill)
───────────────────────────────────
  Trae 字段                  CRUX 字段
  ─────────────────────────────────────────────────
  agentName                 → name
  agentDescription          → description
  agentPrompt               → prompt[0].content
  agentIcon                 → metadata.icon
  agentTools                → metadata.tools
  mcpTools                  → metadata.mcp_servers
  builtinTools              → metadata.builtin_tools
  agentConfig.model         → models[0]
  agentConfig.maxTokens     → metadata.config.max_tokens
  agentConfig.temperature   → metadata.config.temperature

CRUX skill.json 结构:
  {
    "name": "skill-name",
    "description": "...",
    "version": "1.0.0",
    "author": "imported-from-trae",
    "target": "code",
    "models": ["deepseek-v4-flash"],
    "always_load": false,
    "metadata": { ... },
    "prompt": [{ "type": "system", "content": "..." }]
  }
""")


def main():
    if len(sys.argv) < 2:
        cmd_list_tools()
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "import": cmd_import,
        "export": cmd_export,
        "batch": cmd_batch,
        "schema": lambda _: cmd_schema(),
        "help": lambda _: cmd_list_tools(),
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        cmd_list_tools()


if __name__ == "__main__":
    main()
