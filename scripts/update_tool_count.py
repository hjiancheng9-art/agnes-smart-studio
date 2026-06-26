#!/usr/bin/env python3
"""CI 脚本：自动更新 AGENTS.md 中的工具数量 + 生成评分报告。

由 .github/workflows/ci.yml 在 push main 时调用。
执行:
    1. reload_registry() 获取真实工具数
    2. score_all() 生成评分报告
    3. 用正则替换 AGENTS.md 中的旧工具数
    4. 保存 report 到 output/tool_scorecard.json

用法:
    python scripts/update_tool_count.py          # 正常执行（写文件）
    python scripts/update_tool_count.py --check  # 只检查是否需要更新，不写文件
                                                   # RC=0 已对齐 / RC=1 有漂移
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AGENTS_MD = ROOT / "AGENTS.md"

# 精确匹配"工具总数"语境（词边界 + 上下文），避免子串和 "(4 tools)" 误判。
# 捕获组 1 = 数字。后跟边界字符 : , — 或行尾，且前导不是 "(" （排除 "MCP bridge (4 tools)"）
_TOOL_COUNT_PATTERNS = [
    # "84 Tools:" / "84 tools," / "84 tools —" / "84 tools\n"
    re.compile(r"(?<!\()\b(\d{1,3})\s+[Tt]ools\b(?=\s*[:,\u2014\n]|$)"),
    re.compile(r"[Tt]ools:\s*(\d{1,3})\b"),  # "Tools: 84"
]


def get_tool_count() -> int:
    """加载真实 registry 返回工具总数。"""
    from core.tools import ToolRegistry

    reg = ToolRegistry()
    reg.load()
    return len(reg.tool_names)


def generate_scorecard() -> dict:
    """生成评分报告并持久化。"""
    from core import tool_call_log
    from core.tool_scorecard import save_report, score_all
    from core.tools import ToolRegistry

    reg = ToolRegistry()
    reg.load()
    runtime_calls = tool_call_log.group_by_tool()
    report = score_all(reg, runtime_calls=runtime_calls)
    save_report(report)
    return report


def find_stale_counts(content: str, expected: int) -> list[tuple[str, int]]:
    """返回所有与 expected 不符的 (匹配文本, 旧数字) 列表。空表示无漂移。"""
    stale: list[tuple[str, int]] = []
    for pattern in _TOOL_COUNT_PATTERNS:
        for m in pattern.finditer(content):
            old = int(m.group(1))
            if old != expected:
                stale.append((m.group(0), old))
    return stale


def update_agents_md(tool_count: int) -> bool:
    """用正则替换 AGENTS.md 中的工具数。返回是否有变更。"""
    content = AGENTS_MD.read_text(encoding="utf-8")
    stale = find_stale_counts(content, tool_count)
    if not stale:
        return False

    def replace_count(m: re.Match) -> str:
        return m.group(0).replace(m.group(1), str(tool_count), 1)

    new_content = content
    for pattern in _TOOL_COUNT_PATTERNS:
        new_content = pattern.sub(replace_count, new_content)

    if new_content != content:
        AGENTS_MD.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> int:
    check_only = "--check" in sys.argv

    tool_count = get_tool_count()
    report = generate_scorecard()

    print(f"当前工具数: {tool_count}")
    print(f"评分分布: {report['grade_distribution']}")
    print(f"平均分: {report['average_score']}")
    print(f"零测试: {report['untested_count']} 个")

    if check_only:
        content = AGENTS_MD.read_text(encoding="utf-8")
        stale = find_stale_counts(content, tool_count)
        if not stale:
            print(f"AGENTS.md 工具数已是最新 ({tool_count})")
            return 0
        print(f"AGENTS.md 工具数漂移！期望 {tool_count}，发现 {len(stale)} 处不符:")
        for text, old in stale:
            print(f"  - {text!r} (旧值 {old})")
        return 1

    changed = update_agents_md(tool_count)
    if changed:
        print(f"已更新 AGENTS.md 工具数 → {tool_count}")
    else:
        print(f"AGENTS.md 工具数已是最新 ({tool_count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
