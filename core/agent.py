"""智能体增强 — 计划模式 / 子智能体 / 上下文压缩"""

import json
import re
from typing import Iterator


# ── 计划模式系统提示词 ──

PLAN_PROMPT = """你是任务规划师。收到用户需求后，先输出执行计划，再逐步执行。

输出格式：
```plan
1. [步骤名] — 目的：xxx — 工具：tool_name
2. [步骤名] — 目的：xxx — 工具：tool_name
...
```

然后依次执行每个步骤，每步完成后报告结果。

规则：
- 计划要具体，每步写明用什么工具、期望什么结果
- 先思考再行动，不要跳过分析直接写代码
- 完成所有步骤后做总结"""


def parse_plan(text: str) -> list[dict]:
    """从 LLM 输出中解析执行计划"""
    # 提取 ```plan ... ``` 块
    match = re.search(r'```plan\s*\n(.+?)```', text, re.DOTALL)
    if not match:
        return []
    steps = []
    for line in match.group(1).strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # 格式: "1. [名称] — 目的：xxx — 工具：xxx"
        num_match = re.match(r'(\d+)\.\s*(.+)', line)
        if num_match:
            step_text = num_match.group(2)
            # 提取工具名
            tool_match = re.search(r'工具[：:]\s*(\w+)', step_text)
            purpose_match = re.search(r'目的[：:]\s*(.+?)(?:—|$)', step_text)
            name_match = re.match(r'\[(.+?)\]', step_text)
            steps.append({
                "name": name_match.group(1) if name_match else step_text[:30],
                "purpose": purpose_match.group(1).strip() if purpose_match else "",
                "tool": tool_match.group(1) if tool_match else "",
            })
    return steps


# ── 子智能体 ──

SUBAGENT_PROMPT = """你是子智能体，只负责完成指定的子任务，完成后返回结果。

任务：{task}

输出要求：
- 只输出任务结果，不要多余文字
- 如果用了工具，说明工具返回了什么
- 如果失败，报告具体原因"""


def spawn_subagent(client, task: str, model: str = "agnes-2.0-flash") -> str:
    """启动一个子智能体处理独立任务，返回结果文本"""
    from core.tools import get_registry
    tools = get_registry()
    messages = [
        {"role": "system", "content": SUBAGENT_PROMPT.format(task=task)},
        {"role": "user", "content": f"开始执行: {task}"},
    ]
    try:
        r = client.chat(
            model=model, messages=messages, max_tokens=2048,
            tools=tools.definitions if tools.definitions else None,
        )
        return r["choices"][0]["message"]["content"] or "[无输出]"
    except Exception as e:
        return f"[子智能体失败] {e}"


# ── 上下文压缩 ──

COMPRESS_PROMPT = """总结以下对话的关键信息，保留：
- 用户的需求和偏好
- 已完成的步骤和结果
- 重要决策和修正
- 待处理的事项

输出简洁摘要（不超过 500 字）：
"""


def compress_messages(messages: list[dict], client,
                      model: str = "agnes-1.5-flash") -> str:
    """压缩对话历史为摘要"""
    if len(messages) < 6:
        return ""
    # 提取最近的 user/assistant 消息
    recent = []
    for m in messages[1:]:
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if c.get("text"))
        if m.get("role") in ("user", "assistant") and content.strip():
            recent.append(f"{m['role']}: {content[:200]}")

    if len(recent) < 4:
        return ""

    ctx = COMPRESS_PROMPT + "\n".join(recent[-20:])  # 最多 20 轮
    try:
        r = client.chat(model=model, messages=[
            {"role": "user", "content": ctx}
        ], max_tokens=512)
        return r["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


# ── 自动测试 ──

TEST_RUNNER = """#!/usr/bin/env python3
'''''自动生成并运行测试'''''
import sys, os, subprocess, json

def run_tests(test_dir: str = "tests") -> dict:
    result = {"passed": 0, "failed": 0, "errors": [], "output": ""}
    if not os.path.isdir(test_dir):
        result["errors"].append(f"测试目录不存在: {test_dir}")
        return result
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", test_dir, "-q", "--tb=short"],
                           capture_output=True, text=True, timeout=60)
        result["output"] = r.stdout + r.stderr
        # 解析 pytest 输出
        for line in (r.stdout + r.stderr).split("\\n"):
            if "passed" in line.lower() or "failed" in line.lower():
                import re
                p = re.search(r'(\\d+) passed', line)
                f = re.search(r'(\\d+) failed', line)
                result["passed"] = int(p.group(1)) if p else 0
                result["failed"] = int(f.group(1)) if f else 0
    except FileNotFoundError:
        result["errors"].append("pytest 未安装，运行: pip install pytest")
    except Exception as e:
        result["errors"].append(str(e))
    return result

if __name__ == "__main__":
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"
    print(json.dumps(run_tests(test_dir), indent=2, ensure_ascii=False))
"""
