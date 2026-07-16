"""
trae_agent_converter — 在 CRUX Studio 内直接使用的 trae agent ↔ skill.json 转换器

用法:
  /trae-convert <file.json>     导入 trae agent → skill.json
  /trae-export <skill.json>     导出 skill → trae agent 格式
  /trae-batch <dir>             批量转换目录
  /trae-new <name> [desc]       手动创建新 skill

注册方式:
  在 core/plugins.py 或 chat.py 中导入此模块并注册命令
"""

import json
import os
from pathlib import Path

SKILLS_DIR = Path("skills")
TOOLS_DIR = Path("tools")


def cmd_trae_convert(args: list[str]) -> str:
    """导入 trae agent JSON 文件 → skill.json"""
    if not args:
        return "用法: /trae-convert <agent.json>\n从 trae agent JSON 生成 CRUX skill"

    filepath = args[0]
    if not os.path.isfile(filepath):
        return f"文件不存在: {filepath}"

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return f"JSON 解析失败: {e}"

    if isinstance(data, list):
        data = data[0]

    # 调用转换器
    from tools.trae_to_skill import trae_to_skill
    name = data.get("agentName", data.get("name", Path(filepath).stem))
    skill_name = name.lower().replace(" ", "-").replace("_", "-")
    out_path = SKILLS_DIR / f"{skill_name}.skill.json"

    skill = trae_to_skill(data, str(out_path))

    return (
        f"✅ 转换完成！\n"
        f"   源文件: {filepath}\n"
        f"   输出: {out_path}\n"
        f"   Agent: {name}\n"
        f"   Skill: {skill_name}\n\n"
        f"加载试试: skill_load {skill_name}"
    )


def cmd_trae_export(args: list[str]) -> str:
    """导出 skill.json → trae agent 格式"""
    if not args:
        return "用法: /trae-export <skill.json>\n导出 CRUX skill 为 trae agent 格式"

    filepath = args[0]
    if not os.path.isfile(filepath):
        return f"文件不存在: {filepath}"

    out_path = args[1] if len(args) > 1 else filepath.replace(".skill.json", ".trae-agent.json")

    from tools.trae_to_skill import skill_to_trae
    trae = skill_to_trae(filepath, out_path)

    return (
        f"✅ 导出完成！\n"
        f"   源文件: {filepath}\n"
        f"   输出: {out_path}\n"
        f"   Agent: {trae.get('agentName', 'unnamed')}"
    )


def cmd_trae_batch(args: list[str]) -> str:
    """批量转换目录下所有 JSON"""
    if not args:
        return "用法: /trae-batch <input_dir> [output_dir]\n批量转换 trae agent JSON → skill.json"

    input_dir = args[0]
    output_dir = args[1] if len(args) > 1 else "skills"

    if not os.path.isdir(input_dir):
        return f"目录不存在: {input_dir}"

    from tools.trae_to_skill import batch_convert
    results = batch_convert(input_dir, output_dir)

    lines = [f"✅ 批量转换完成: {len(results)} 个"]
    for src, dst, status in results:
        lines.append(f"   {'✓' if status == 'ok' else '✗'} {src} → {dst}")

    return "\n".join(lines)


def cmd_trae_new(args: list[str]) -> str:
    """手动创建一个 agent 并转为 skill.json"""
    if not args:
        return "用法: /trae-new <name> [description]\n手动创建新 agent skill"

    name = args[0]
    desc = args[1] if len(args) > 1 else f"{name} agent"

    return (
        f"准备创建 agent: {name}\n"
        f"描述: {desc}\n\n"
        f"请提供系统提示词 (prompt)，或者在命令行执行:\n"
        f"  python tools/trae_to_skill.py import \"{name}\" \"{desc}\"\n"
        f"然后粘贴 prompt 内容。"
    )


def register_commands(register_fn):
    """注册到 CRUX 命令系统"""
    register_fn("trae-convert", cmd_trae_convert, "导入 trae agent → skill.json")
    register_fn("trae-export", cmd_trae_export, "导出 skill → trae agent 格式")
    register_fn("trae-batch", cmd_trae_batch, "批量转换 trae agents")
    register_fn("trae-new", cmd_trae_new, "手动创建 agent skill")


# 命令列表供 chat.py 直接使用
COMMANDS = {
    "trae-convert": cmd_trae_convert,
    "trae-export": cmd_trae_export,
    "trae-batch": cmd_trae_batch,
    "trae-new": cmd_trae_new,
}
