"""
Version module — 单一版本真源 (single source of truth).

所有需要展示应用版本号的地方都应从这里导入 __version__，
不要再在各处硬编码版本字符串（曾出现 pyproject=3.0 / manifest=5.0 /
launcher=5.0 / engine=2.0 四分五裂的历史）。
"""

__version__ = "6.1.0"
VERSION = __version__  # 向后兼容旧调用

# ── 版本标识 ──────────────────────────────────────────
VERSION_TAG = f"v{__version__}"
BUILD_LABEL = "CRUX Studio"

# ── v6.1 改进指标 ──────────────────────────────────────
V6_METRICS = {
    "tests_total": 1708,
    "tests_failed": 0,
    "new_tests_v61": 49,
    "bugs_fixed": 30,
    "closed_loops": 19,
    "dead_code_removed": 3500,
    "tmp_files_cleaned": 33,
    "ux_improvements": 6,
    "auto_skills": 6,
    "root_files_cleaned": 211,
    "test_files": 181,
}

V6_HIGHLIGHTS = [
    "19 个闭环全部端到端激活（智能体/技能/TRM/Dashboard/错误分级）",
    "30+ bug 修复：滚动失效/输入崩溃/并发冲突/静默消息丢弃",
    "6 项交互打磨：工具序号/系统消息/长输出折叠/错误分级/能力说明/轮次摘要",
    "清债 3,500 行死代码 + 33 临时文件 + 1 损坏文件",
    "49 个新测试覆盖 ThinkingPanel/输入清洗/活动日志/错误分类",
    "工作区感知：CRUX_WORKSPACE 环境变量 + system prompt 注入",
    "6 个技能自动加载：caliber/code-reviewer/code-guardian/tdd/python-anti-patterns/security-hardening",
    "全局 code-guardian 技能安装到 Claude Code",
]


def get_version_info() -> dict:
    """返回版本和状态信息的字典，供欢迎屏和 API 使用。"""
    parts = __version__.split(".")
    return {
        "version": __version__,
        "major": int(parts[0]),
        "minor": int(parts[1]) if len(parts) > 1 else 0,
        "patch": int(parts[2]) if len(parts) > 2 else 0,
        "tag": VERSION_TAG,
        "label": BUILD_LABEL,
        "metrics": V6_METRICS,
        "highlights": V6_HIGHLIGHTS,
    }
