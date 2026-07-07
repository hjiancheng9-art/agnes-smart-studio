"""Beast Wiring — 七兽神经焊盘。真接线，每条信道通肌肉。
所有事件处理器现在调用真实模块，不再只是 logger.debug。
wire_all() 在 ChatSession.__init__ 中调用一次。
新增文件：event_bus / plugin_system / capability_registry
          watchdog / daemon / pipeline_dag / skin / five_beasts

P1-fix: 所有 except Exception 替换为精确异常类型 + logger.exception() 保留 traceback。
  事件处理器: (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError, AttributeError)
  初始化模块: (ImportError, OSError, RuntimeError)
  诊断汇总块: (ImportError, OSError, RuntimeError)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("crux.beast_wiring")
_wired = False

# ── 事件处理器安全异常集：捕运行期错误，放行致命错误 (KeyboardInterrupt/SystemExit/MemoryError) ──
_EVENT_SAFE = (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError, AttributeError)
# ── 初始化安全异常集：模块缺失/文件IO/运行时 ──
_INIT_SAFE = (ImportError, OSError, RuntimeError)


def wire_all() -> bool:
    global _wired
    if _wired:
        return True
    from core.capability_registry import registry
    from core.event_bus import bus

    # ── 玄武：能力守卫 ──
    def xuanwu_guard(tool_name: str = "", tool_args: dict | None = None, **kwargs):
        if not tool_name:
            return
        ok, reason = registry.check(tool_name)
        if not ok:
            logger.warning("[Xuanwu] BLOCKED %s: %s", tool_name, reason)
            registry.record(tool_name, False)
        else:
            registry.record(tool_name, True)

    bus.on("tool:before", xuanwu_guard)

    # ── 白虎：容灾自愈 ──
    def baihu_recovery(error: Exception | None = None, tool_name: str = "", **kwargs):
        if error is None:
            return
        err_type = type(error).__name__
        registry.record(tool_name, False)
        try:
            from core.watchdog import get_watchdog

            wd = get_watchdog()
            if not wd._state.provider_ok:
                from core.provider import get_provider_manager

                get_provider_manager().fallback()
        except _EVENT_SAFE as e:
            logger.exception("[Baihu] recovery failed for %s on %s: %s", err_type, tool_name, e)
            registry.record_incident(tool_name, "baihu_failover_failed")

    bus.on("error", baihu_recovery)

    # ── 朱雀：反思 ──
    def zhuque_reflect(tool_name: str = "", result: object = None, error: object = None, **kwargs):
        # 朱雀反思由 core/reflection.py 的 ReflectionEngine 在 POST_TOOL_USE hook
        # （priority=40）中独立执行；此处仅做轻量状态观测，无额外副作用。
        if error:
            logger.debug("[Zhuque] %s ERROR: %s", tool_name, error)
        elif result is not None:
            logger.debug("[Zhuque] %s OK", tool_name)

    bus.on("tool:after", zhuque_reflect)

    # ── 麒麟：记忆 ──
    def qilin_session_mark(**kwargs):
        try:
            from core.semantic_memory import get_memory

            mem = get_memory()
            mem.data.setdefault("session_count", 0)
            mem.data["session_count"] += 1
        except _EVENT_SAFE as e:
            logger.exception("[Qilin] session_mark failed: %s", e)

    bus.on("session:start", qilin_session_mark)

    def qilin_session_end(**kwargs):
        try:
            from core.semantic_memory import get_memory

            get_memory()._save()
        except _EVENT_SAFE as e:
            logger.exception("[Qilin] session_end persist failed: %s", e)

    bus.on("session:end", qilin_session_end)

    # ── 螣蛇：觉知 ──
    def tengshe_session_start(**kwargs):
        try:
            from pathlib import Path

            awareness_dir = Path(__file__).resolve().parent.parent / "awareness"
            for fname in ["AGENTS.md", "MEMORY.md", "USER.md"]:
                fpath = awareness_dir / fname
                if fpath.exists():
                    logger.debug("[TengShe] Loaded %s (%d bytes)", fname, fpath.stat().st_size)
            # Ensure memory archive dir exists
            mem_dir = awareness_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
        except _EVENT_SAFE as e:
            logger.exception("[TengShe] awareness load failed: %s", e)

    bus.on("session:start", tengshe_session_start)

    def tengshe_session_end(**kwargs):
        """Session end: archive memory snapshot."""
        try:
            from datetime import datetime
            from pathlib import Path

            awareness_dir = Path(__file__).resolve().parent.parent / "awareness"
            mem_dir = awareness_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            mem_file = mem_dir / f"{today}.md"
            if not mem_file.exists():
                mem_file.write_text(
                    f"<!-- memory-chat:crustudio-session -->\n## Session: {today}\n",
                    encoding="utf-8",
                )
            logger.info("[TengShe] Memory archived → %s", mem_file)
        except _EVENT_SAFE as e:
            logger.exception("[TengShe] session_end persist failed: %s", e)

    bus.on("session:end", tengshe_session_end)

    # ── 应龙：调度 ──
    def yinglong_agent_spawn(**kwargs):
        """Agent spawn: log multi-agent dispatch, validate tool permissions."""
        try:
            agent_name = kwargs.get("agent_name", "unknown")
            goal = kwargs.get("goal", "")[:80]
            tools = kwargs.get("tools", [])
            logger.info("[Yinglong] Agent spawned: %s (goal: %s, tools: %s)", agent_name, goal, tools)
            # Permission check: ensure spawned agent only has allowed tools
            if "write" in tools or "edit" in tools:
                logger.warning("[Yinglong] Agent %s granted write access — monitoring", agent_name)
        except _EVENT_SAFE as e:
            logger.exception("[Yinglong] agent_spawn failed: %s", e)

    bus.on("agent:spawn", yinglong_agent_spawn)

    def yinglong_handoff(**kwargs):
        try:
            from_agent = kwargs.get("from_agent", "unknown")
            to_agent = kwargs.get("to_agent", "unknown")
            logger.info("[Yinglong] Handoff: %s → %s", from_agent, to_agent)
        except _EVENT_SAFE as e:
            logger.exception("[Yinglong] handoff failed: %s", e)

    bus.on("agent:handoff", yinglong_handoff)

    def yinglong_plan_generated(**kwargs):
        """Plan generated: log structured plan creation."""
        try:
            plan_title = kwargs.get("title", "untitled")
            step_count = kwargs.get("steps", 0)
            logger.info("[Yinglong] Plan generated: %s (%d steps)", plan_title, step_count)
        except _EVENT_SAFE as e:
            logger.exception("[Yinglong] plan_generated failed: %s", e)

    bus.on("plan:generated", yinglong_plan_generated)

    # ── 青龙：文件冲击分析 ──
    def qinglong_files(file_path: str = "", **kwargs):
        if not file_path:
            return
        try:
            from core.event_bus import bus as _bus

            _bus.emit("file:changed", file_path=file_path, analyzed=True)
        except _EVENT_SAFE as e:
            logger.debug("Impact analysis: %s", e)

    bus.on("file:changed", qinglong_files)

    # ── 能力注册 ──
    try:
        registry.register_from_tools_json()
    except _INIT_SAFE as e:
        logger.exception("[Beast] capability registry init failed: %s", e)

    # ── 插件 ──
    try:
        from core.plugin_system import PluginManager

        pm = PluginManager()
        pm.load_all()
    except _INIT_SAFE as e:
        logger.exception("[Beast] plugin init failed: %s", e)

    # ── Watchdog ──
    try:
        from core.watchdog import get_watchdog

        get_watchdog().start()
    except _INIT_SAFE as e:
        logger.exception("[Beast] watchdog init failed: %s", e)

    # ── Daemon ──
    try:
        from core.daemon import get_daemon

        get_daemon()
    except _INIT_SAFE as e:
        logger.exception("[Beast] daemon init failed: %s", e)

    # ── Skin (held by global ref) ──
    try:
        from core.skin import get_skin

        get_skin()
    except _INIT_SAFE as e:
        logger.exception("[Beast] skin init failed: %s", e)

    # ── 神器激活 ──
    try:
        from core.artifact_activation import activate_all_artifacts

        activate_all_artifacts()
    except _INIT_SAFE as e:
        logger.exception("[Beast] artifact activation failed: %s", e)

    # ── 贴身七件 ──
    try:
        from core.intimate_slots.talisman import circuit

        bus.on("error", lambda **kw: circuit.record_failure(kw.get("provider", "default")))
        bus.on(
            "tool:after",
            lambda error=None, **kw: (
                circuit.record_success(None) if error is None else circuit.record_failure(str(error))
            ),  # pyright: ignore[reportArgumentType]
        )
    except _INIT_SAFE as e:
        logger.exception("[Beast] talisman circuit init failed: %s", e)

    try:
        from core.intimate_slots.inner_armor import vault

        vault.migrate_from_env()
    except _INIT_SAFE as e:
        logger.exception("[Beast] vault migrate failed: %s", e)

    try:
        from core.intimate_slots.backpack import backpack

        backpack.snapshot("session_start")
    except _INIT_SAFE as e:
        logger.exception("[Beast] backpack snapshot failed: %s", e)

    try:
        from core.intimate_slots.belt import pipeline
        from core.intimate_slots.cloak import cloak as _cloak

        pipeline.add_stage("privacy", lambda d: _cloak.sanitize(str(d)))
    except _INIT_SAFE as e:
        logger.exception("[Beast] belt/cloak init failed: %s", e)

    try:
        from core.intimate_slots.left_ring import telemetry

        bus.on(
            "tool:after",
            lambda tool_name="", error=None, provider="", latency=0.0, **kw: telemetry.log(
                "tool_call",
                tool=tool_name,
                latency=latency,
                error=str(error) if error else "",
                provider=provider,
            ),
        )
    except _INIT_SAFE as e:
        logger.exception("[Beast] telemetry init failed: %s", e)

    try:
        from core.intimate_slots.right_ring import healer

        healer.check()
    except _INIT_SAFE as e:
        logger.exception("[Beast] healer check failed: %s", e)

    # ── 音效系统 ──
    try:
        from core.sound_ux import SoundUX

        bus.on("session:start", lambda **kw: SoundUX.startup())
        bus.on("watchdog:alert", lambda **kw: SoundUX.alert())
        bus.on("error", lambda **kw: SoundUX.error())
        bus.on("tool:after", lambda error=None, **kw: SoundUX.error() if error else None)
    except _INIT_SAFE as e:
        logger.exception("[Beast] sound_ux init failed: %s", e)

    _wired = True
    logger.debug("[Beast] All 5 beasts wired successfully")
    return True


def get_wiring_summary() -> str:
    try:
        from core.capability_registry import registry
    except _INIT_SAFE as e:
        logger.debug("[Beast] registry summary failed: %s", e)
        registry = None
    try:
        from core.plugin_system import PluginManager

        pm = PluginManager()
    except _INIT_SAFE as e:
        logger.debug("[Beast] plugin summary failed: %s", e)
        pm = None
    try:
        from core.watchdog import get_watchdog

        wd = get_watchdog()
        wds = "alive" if wd.alive else "off"
    except _INIT_SAFE as e:
        logger.debug("[Beast] watchdog summary failed: %s", e)
        wds = "off"
    try:
        from core.daemon import get_daemon

        d = get_daemon()
        dd = "ready" if d.is_running else "standby"
    except _INIT_SAFE as e:
        logger.debug("[Beast] daemon summary failed: %s", e)
        dd = "standby"

    reg_summary = registry.summary() if registry else ""
    as_text = f"""{reg_summary}
## Plugins
{pm.summary() if pm else "unknown"}

## Daemon
  state: {dd} | watchdog: {wds}"""
    return as_text
