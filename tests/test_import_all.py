"""Smoke test — 验证全部核心模块可导入，无 import 环或语法错误。

设计原则：
- 仅做 import，不实例化（避免网络/文件依赖）
- 按依赖顺序排列，早期失败不阻塞后续
- 单个模块失败不中断整体，输出详细报告
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORE_MODULES = [
    # 基础——先导（无内部依赖）
    "core.version", "core.config", "core.constraints", "core.event_bus",
    # 供应商 + 客户端
    "core.provider", "core.client",
    # 技能 + 市场
    "core.skills", "core.marketplace",
    # 规则 + hooks
    "core.rules", "core.hooks",
    # 工具系统
    "core.tools", "core.sandbox", "core.context_tools", "core.cost_tracker",
    # 韧性 + 恢复
    "core.resilience", "core.recovery",
    # 智能体基础设施
    "core.observability", "core.semantic_memory",
    # 代码智能
    "core.code_intel",
    # 自审计 + 自修
    "core.self_audit", "core.patch",
    # 引擎
    "engines", "engines.text_to_image", "engines.video",
    # prompt 系统
    "core.chat_prompt",
    # 核心 chat
    "core.chat", "core.async_chat",
    # 智能调度
    "core.router", "core.orchestra",
    # 插件 + 能力
    "core.plugin_system", "core.capability", "core.capability_registry",
    # Git / GitHub
    "core.git_tools", "core.git_workflow", "core.github_tools",
    # 工具集
    "core.file_tools", "core.browser_tools", "core.audio_tools",
    "core.comfyui_tools", "core.mcp_client", "core.mcp_server",
    "core.codex_tools", "core.codex_engines",
    # 守护进程
    "core.watchdog", "core.daemon",
    # 五兽躯体
    "core.beast_wiring", "core.seven_beasts_fusion", "core.skin", "core.sound_ux",
    # 管线
    "core.pipeline_dag", "core.pipeline_tools", "core.pipeline_state",
    # 记忆 / 反思 / 脑
    "core.reflection", "core.brain",
    # 神器
    "core.artifact_activation", "core.prompt_bypass", "core.prompt_lab",
    "core.golden_finger",
    # Web
    "core.web_browser", "core.web_api",
    # 启动
    "core.startup_checks",
    # 执行器
    "core.executor",
    # 谱系（lore）
    "core.lore.crux_dna", "core.lore.codex_dna", "core.lore.claude_dna",
    "core.lore.codebuddy_dna", "core.lore.zcode_dna",
]


def _do_imports():
    passed = 0
    failed = []
    for mod_path in CORE_MODULES:
        try:
            __import__(mod_path)
            passed += 1
        except Exception as e:
            failed.append(f"{mod_path}: {type(e).__name__}: {e}")
    return passed, failed


def test_all_imports():
    """测试所有核心模块可导入。"""
    passed, failed = _do_imports()
    assert len(failed) == 0, \
        f"Failed imports ({len(failed)}/{passed + len(failed)}): {failed}"
