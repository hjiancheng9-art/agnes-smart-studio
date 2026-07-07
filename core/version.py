"""
Version module — 单一版本真源 (single source of truth).

所有需要展示应用版本号的地方都应从这里导入 __version__，
不要再在各处硬编码版本字符串（曾出现 pyproject=3.0 / manifest=5.0 /
launcher=5.0 / engine=2.0 四分五裂的历史）。
"""

__version__ = "6.0.0"
VERSION = __version__  # 向后兼容旧调用

# ── 版本标识 ──────────────────────────────────────────
VERSION_TAG = f"v{__version__}"
BUILD_LABEL = "CRUX Studio"

# ── v6.0 改进指标（展示于欢迎屏 / status API） ──────────
V6_METRICS = {
    "tests_total": 1659,
    "tests_failed": 0,
    "ruff_remaining": 177,
    "root_files_cleaned": 178,
    "wiki_pages": 14,
    "test_files": 71,
    "ci_stages": 3,
    "ai_score_before": 8.1,
    "ai_score_after": 8.9,
}

V6_HIGHLIGHTS = [
    "CI/CD Pipeline: lint → test → security (GitHub Actions)",
    "测试 1659 全绿, 0 失败 (v5.0 基线 9 failures)",
    "ruff 修复 1000+ 问题, 剩 177 手动项",
    "根目录 178 个散文件归档清理",
    "Wiki 知识库 14 篇: 架构/TRM/CDP/ComfyUI/Agent/测试/Onboarding",
    "event_bus / event_log / adr_engine 测试覆盖新增",
    "AI 三方评审评分: 8.1 → 8.9 (+0.8)",
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
