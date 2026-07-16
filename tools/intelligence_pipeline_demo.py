"""
CRUX Intelligence Pipeline — 端到端示例
======================================
演示 IntelligencePolicyRouter → DeliberateWorkflow 完整流程。

运行: python -m demos.intelligence_pipeline_demo
"""

import asyncio

from core.critic_agent import (
    CritiqueCategory,
    CritiqueFinding,
    CritiqueReport,
    CritiqueSeverity,
)
from core.deliberate_workflow import DeliberateWorkflow, WorkflowResult
from core.intelligence_policy import IntelligencePolicyRouter


async def main():
    print("=" * 60)
    print("CRUX Intelligence Pipeline — Demo")
    print("=" * 60)

    router = IntelligencePolicyRouter()

    # ── 测试请求 ──
    requests = [
        ("简单问候", "你好"),
        ("写函数", "帮我写一个 Python 函数，计算斐波那契数列"),
        (
            "重构架构",
            """帮我把用户认证模块从 session 改为 JWT。
首先，分析现有的认证流程。
然后，设计新的 JWT 方案。
接着，迁移所有相关代码。
最后，写单元测试验证。""",
        ),
        ("安全删除", "帮我删除所有用户的密码记录并重置数据库"),
        ("研究LLM", "研究一下最新的 RAG 技术和向量数据库选型"),
        ("UI设计", "帮我设计一个现代化、简约风格的产品落地页"),
    ]

    for desc, req in requests:
        print(f"\n{'─' * 50}")
        print(f"📝 {desc}")
        print(f"   请求: {req[:80]}...")

        # 路由分析
        mode = router.route(req)
        profile = router.analyze(req)

        print(f"   🎯 路由: {mode.value}")
        print(f"   📊 复杂度: {profile.complexity} 代码: {profile.has_code} 多步: {profile.has_multi_step}")
        print(f"   🛡️ 安全: {profile.security_risk} 破坏: {profile.destructive_risk} 创意: {profile.creative_load}")
        print(f"   🔬 研究: {profile.needs_research} 置信度: {profile.confidence:.2f}")

    # ── 工作流演示 ──
    print(f"\n{'=' * 60}")
    print("📋 DeliberateWorkflow — 模拟 DEEP 模式")
    print("=" * 60)

    workflow = DeliberateWorkflow()
    wf_result = WorkflowResult(mode="DEEP", passed=True, goal_id="demo-001")

    # 添加模拟步骤
    mock_steps = [
        ("policy_analysis", "success", "模式=DEEP, 置信度=0.67"),
        ("plan", "success", "生成 5 个执行步骤"),
        ("attack", "success", "发现 3 个边界条件"),
        ("criticize", "success", "2 个 high, 1 个 medium"),
        ("repair", "success", "修复 2 个 high 问题"),
        ("verify", "success", "所有检查通过"),
    ]
    import time

    for name, status, result in mock_steps:
        step = wf_result.steps.__class__(name=name, status=status, result=result)
        step.started_at = time.time() - 1
        step.completed_at = time.time()
        wf_result.steps.append(step)

    # 添加模拟审查报告
    report = CritiqueReport(target="认证模块JWT迁移")
    report.findings.append(
        CritiqueFinding(
            category=CritiqueCategory.SECURITY,
            severity=CritiqueSeverity.HIGH,
            summary="JWT secret 不应硬编码",
            location="auth/jwt_handler.py:12",
            suggestion="从环境变量读取 JWT_SECRET",
        )
    )
    report.findings.append(
        CritiqueFinding(
            category=CritiqueCategory.LOGIC,
            severity=CritiqueSeverity.MEDIUM,
            summary="token 过期后没有 refresh 机制",
            location="auth/token.py:45",
            suggestion="添加 refresh_token 端点",
        )
    )
    wf_result.critique_report = report
    wf_result.summary = "所有 2 个 high 问题已修复，审查通过"

    # 格式化输出
    print(workflow.format_result_for_user(wf_result))

    # ── 统计 ──
    print(f"\n{'=' * 60}")
    print("📈 路由统计")
    stats = router.get_stats()
    for mode, count in sorted(stats.items()):
        print(f"   {mode}: {count}")

    print(f"\n{'=' * 60}")
    print("✅ Intelligence Pipeline Demo 完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
