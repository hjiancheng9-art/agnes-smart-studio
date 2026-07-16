"""Session hook wiring for ChatSession (refactor P1).

Extracts the Phase 1-14 hook registration + subsystem activation out of
ChatSession.__init__ into a single entry point. Everything is set on the
passed ``session`` object, so behavior and ordering are identical to the
inline version. Each block is independently guarded; a failing hook only
logs and never blocks session construction.
"""

from __future__ import annotations

import logging

from core.intelligence_hook import IntelligenceHook
from core.vision_context import VisionContext

logger = logging.getLogger("crux")


def wire_session_hooks(session) -> None:
    """Register all global + session-scoped hooks for a ChatSession.

    Sets attributes on ``session`` (tvl, vision_ctx, _pN_*_hooked flags,
    _intelligence_hook, _adaptive_learner, ...). Never raises.
    """
    # 七兽躯体激活
    try:
        from core.beast_wiring import wire_all

        wire_all()
    except (ImportError, OSError):
        logger.debug("spectrum module not available")
    # 激活学习钩子（agent 从工具成败中学习）
    try:
        from core.hooks import register_learning_hooks

        register_learning_hooks()
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass
    # 激活工具拦截器（PreToolUse 安全守卫）
    try:
        from core.tool_interceptor import register_tool_interceptor

        register_tool_interceptor()
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass
    # 启动配置热重载（models.json + tools.json 变更自动生效）
    try:
        from core.settings_watcher import start_watcher

        start_watcher()
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass
    # 激活三层防御（PreCheck + CircuitBreaker + PostValidate + AutoRollback）
    try:
        from core.defense import register_defense_hooks

        register_defense_hooks()
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass
    # 注入会话上下文（git 分支/状态/最近提交）— 仅在代码/Agent 模式下
    if session.code_mode or session.agent_mode:
        try:
            ctx = session._build_session_context()
            if ctx:
                session.messages[0]["content"] += ctx
        except (OSError, RuntimeError):
            logger.debug("session context injection failed", exc_info=True)
    # 视觉上下文管理器（图片持久化 + 按需重查）
    session.vision_ctx = VisionContext()

    # ── Phase 1: Tool validation + self-correction layer ──
    try:
        from core.tool_validation_integration import ValidationLayer

        session.tvl = ValidationLayer(
            schema_provider=session._get_schema_for_tool,
            max_retries=3,
        )
    except Exception as e:
        logger.warning("Tool validation layer init failed: %s", e)
        session.tvl = None

    # ── Phase 3: Context memory hooks ──
    try:
        from core.context_memory_hooks import inject_context_hooks

        inject_context_hooks(session)
    except Exception as e:
        logger.warning("Context memory hooks init failed: %s", e)

    # ── Phase 4: Reviewer agent hooks ──
    try:
        from core.reviewer_hooks import inject_reviewer_hooks

        inject_reviewer_hooks(session)
    except Exception as e:
        logger.warning("Reviewer hooks init failed: %s", e)

    # ── Phase 5: Skill / Prompt compiler hooks ──
    try:
        from core.skill_compiler_hooks import inject_skill_compiler_hooks

        inject_skill_compiler_hooks(session)
    except Exception as e:
        logger.warning("Skill compiler hooks init failed: %s", e)

    # ── Phase 6: Telemetry + Config ──
    session._p6_telemetry_hooked = True

    # ── Phase 8: Policy router ──
    session._p8_policy_hooked = True

    # ── Phase 9: Project intelligence ──
    session._p9_project_hooked = True

    # ── Phase 10: Trace debugger ──
    session._p10_trace_hooked = True

    # ── Phase 11: Failure learning loop ──
    session._p11_failure_learning_hooked = True

    # ── Phase 12: Benchmark arena ──
    session._p12_benchmark_hooked = True

    # ── Phase 13: Field arena ──
    session._p13_field_arena_hooked = True

    # ── Phase 14: Intelligence Pipeline ──
    session._intelligence_hook = IntelligenceHook()
    session._intel_mode = "BALANCED"
    session._intel_analysis = {}
    session._intel_config = {}
    session._pipeline_result = None

    # ── Prompt Lab: 会话级变体分配 ──
    try:
        from core.prompt_lab import get_prompt_lab

        get_prompt_lab().assign_variant()
    except ImportError as e:
        logger.debug("Prompt lab not available: %s", e)

    # ── Adaptive Learner: 初始化学习引擎 ──
    try:
        from core.adaptive_learner import AdaptiveLearner

        session._adaptive_learner = AdaptiveLearner()
    except ImportError:
        session._adaptive_learner = None
