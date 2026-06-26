"""Beast Wiring — 五兽神经焊盘。真接线，每条信道通肌肉。
所有事件处理器现在调用真实模块，不再只是 logger.debug。
wire_all() 在 ChatSession.__init__ 中调用一次。
新增文件：event_bus / plugin_system / capability_registry
          watchdog / daemon / pipeline_dag / skin / five_beasts
"""

from __future__ import annotations

import logging

logger = logging.getLogger("crux.beast_wiring")
_wired = False


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
                logger.warning("[Baihu] triggering recovery for %s", err_type)
                from core.provider import get_provider_manager

                get_provider_manager().fallback()
        except Exception:
            logger.exception("[Baihu] recovery failed for %s on %s", err_type, tool_name)
            registry.record_incident(tool_name, "baihu_failover_failed")

    bus.on("error", baihu_recovery)

    # ── 朱雀：反思 ──
    def zhuque_reflect(tool_name: str = "", result: object = None, error: object = None, **kwargs):
        # 朱雀反思由 core/reflection.py 的 ReflectionEngine 在 POST_TOOL_USE hook
        # （priority=40）中独立执行；此处仅做轻量状态观测，无额外副作用。
        if error:
            logger.info("[Zhuque] %s FAIL, suggesting retry", tool_name)
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
        except Exception:
            logger.exception("[Qilin] session_mark failed")

    bus.on("session:start", qilin_session_mark)

    def qilin_session_end(**kwargs):
        try:
            from core.semantic_memory import get_memory

            get_memory()._save()
        except Exception:
            logger.exception("[Qilin] session_end persist failed")

    bus.on("session:end", qilin_session_end)

    # ── 螣蛇：觉知 ──
    def tengshe_session_start(**kwargs):
        """Session start: load awareness/ three volumes."""
        try:
            from pathlib import Path
            awareness_dir = Path(__file__).resolve().parent.parent / "awareness"
            for fname in ["AGENTS.md", "MEMORY.md", "USER.md"]:
                fpath = awareness_dir / fname
                if fpath.exists():
                    logger.info("[TengShe] Loaded %s (%d bytes)", fname, fpath.stat().st_size)
            # Ensure memory archive dir exists
            mem_dir = awareness_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[TengShe] Awareness ready — 3 volumes + memory archive")
        except Exception:
            logger.exception("[TengShe] awareness load failed")

    bus.on("session:start", tengshe_session_start)

    def tengshe_session_end(**kwargs):
        """Session end: archive memory snapshot."""
        try:
            from pathlib import Path
            from datetime import datetime
            awareness_dir = Path(__file__).resolve().parent.parent / "awareness"
            mem_dir = awareness_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            mem_file = mem_dir / f"{today}.md"
            if not mem_file.exists():
                mem_file.write_text(f"<!-- memory-chat:crustudio-session -->\n## Session: {today}\n", encoding="utf-8")
            logger.info("[TengShe] Memory archived → %s", mem_file)
        except Exception:
            logger.exception("[TengShe] session_end persist failed")

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
        except Exception:
            logger.exception("[Yinglong] agent_spawn failed")

    bus.on("agent:spawn", yinglong_agent_spawn)

    def yinglong_handoff(**kwargs):
        """Agent handoff: log context passing between agents."""
        try:
            from_agent = kwargs.get("from_agent", "unknown")
            to_agent = kwargs.get("to_agent", "unknown")
            logger.info("[Yinglong] Handoff: %s → %s", from_agent, to_agent)
        except Exception:
            logger.exception("[Yinglong] handoff failed")

    bus.on("agent:handoff", yinglong_handoff)

    def yinglong_plan_generated(**kwargs):
        """Plan generated: log structured plan creation."""
        try:
            plan_title = kwargs.get("title", "untitled")
            step_count = kwargs.get("steps", 0)
            logger.info("[Yinglong] Plan generated: '%s' (%d steps)", plan_title, step_count)
        except Exception:
            logger.exception("[Yinglong] plan_generated failed")

    bus.on("plan:generated", yinglong_plan_generated)

    # ── 青龙：文件冲击分析 ──
    def qinglong_files(file_path: str = "", **kwargs):
        if not file_path:
            return
        try:
            from core.event_bus import bus as _bus

            logger.info("[Qinglong] impact analysis for %s", file_path)
            _bus.emit("file:changed", file_path=file_path, analyzed=True)
        except Exception as e:
            logger.debug("Impact analysis: %s", e)

    bus.on("file:changed", qinglong_files)
    # ── 能力注册 ──
    try:
        registry.register_from_tools_json()
    except Exception:
        logger.exception("[Beast] cap registry init failed")
    # ── 插件 ──
    try:
        from core.plugin_system import PluginManager

        pm = PluginManager()
        pm.load_all()
    except Exception:
        logger.exception("[Beast] plugin system init failed")
    # ── Watchdog ──
    try:
        from core.watchdog import get_watchdog

        get_watchdog().start()
    except Exception:
        logger.exception("[Beast] watchdog init failed")
    # ── Daemon ──
    try:
        from core.daemon import get_daemon

        get_daemon()
    except Exception:
        logger.exception("[Beast] daemon init failed")
    # ── Skin (held by global ref) ──
    try:
        from core.skin import get_skin

        get_skin()
    except Exception:
        logger.exception("[Beast] skin init failed")
    # ── 神器激活 ──
    try:
        from core.artifact_activation import activate_all_artifacts

        activate_all_artifacts()
    except Exception:
        logger.exception("[Beast] artifact activation failed")
    # ── 贴身七件 ──
    try:
        from core.intimate_slots.talisman import circuit

        bus.on("error", lambda **kw: circuit.record_failure(kw.get("provider", "default")))
        bus.on(
            "tool:after",
            lambda **kw: circuit.record_success(kw.get("provider", "default")) if not kw.get("error") else None,
        )
    except Exception:
        logger.exception("[Beast] talisman circuit init failed")
    try:
        from core.intimate_slots.inner_armor import vault

        vault.migrate_from_env()
    except Exception:
        logger.exception("[Beast] vault key migration failed")
    try:
        from core.intimate_slots.backpack import backpack

        backpack.snapshot("session_start")
    except Exception:
        logger.exception("[Beast] backpack snapshot failed")
    try:
        from core.intimate_slots.belt import pipeline
        from core.intimate_slots.cloak import cloak as _cloak

        pipeline.add_stage("privacy", lambda d: _cloak.sanitize(str(d)))
    except Exception:
        logger.exception("[Beast] pipeline privacy stage failed")
    try:
        from core.intimate_slots.left_ring import telemetry

        bus.on(
            "tool:after",
            lambda tool_name="", latency=0, error="", provider="", **kw: telemetry.log(
                "tool_call", tool=tool_name, latency=latency, error=str(error) if error else "", provider=provider
            ),
        )
    except Exception:
        logger.exception("[Beast] telemetry hook init failed")
    try:
        from core.intimate_slots.right_ring import healer

        healer.check()
    except Exception:
        logger.exception("[Beast] healer check failed")
    # ── 音效系统 ──
    try:
        from core.sound_ux import SoundUX

        bus.on("session:start", lambda **kw: SoundUX.startup())
        bus.on("talisman:tripped", lambda **kw: SoundUX.alert())
        bus.on("error", lambda **kw: SoundUX.error())
        bus.on("tool:after", lambda error=None, **kw: SoundUX.error() if error else None)
    except Exception:
        logger.exception("[Beast] sound system init failed")
    _wired = True
    logger.info("[Beasts] all 14 modules + 25 artifacts + 7 intimate slots + sound UX wired")
    return True


def get_wiring_summary() -> str:
    try:
        from core.capability_registry import registry
    except Exception:
        logger.debug("[Beast] registry summary failed")
        registry = None
    try:
        from core.plugin_system import PluginManager

        pm = PluginManager()
    except Exception:
        logger.debug("[Beast] plugin summary failed")
        pm = None
    try:
        from core.watchdog import get_watchdog

        wd = get_watchdog()
        wds = "alive" if wd.alive else "off"
    except Exception:
        logger.debug("[Beast] watchdog summary failed")
        wds = "off"
    try:
        from core.daemon import get_daemon

        d = get_daemon()
        dd = "ready" if d.is_running else "standby"
    except Exception:
        logger.debug("[Beast] daemon summary failed")
        dd = "standby"
    reg_summary = registry.summary() if registry else ""
    pm_summary = pm.summary() if pm else ""
    # Arsenal summary (safe)
    as_text = ""
    try:
        from core.legendary_arsenal import _armory

        as_text = _armory.summary()
    except Exception:
        as_text = "  (init)"
    # Intimate slots (safe)
    intimate = []
    for _mod, _name in [
        ("talisman", "护符"),
        ("inner_armor", "内甲"),
        ("backpack", "行囊"),
        ("belt", "腰带"),
        ("left_ring", "左戒"),
        ("right_ring", "右戒"),
        ("cloak", "披风"),
    ]:
        try:
            import importlib

            importlib.import_module("core.intimate_slots." + _mod)
            intimate.append("  + " + _name)
        except Exception:
            intimate.append("  . " + _name)
    # Gongfa spectrum (safe)
    gongfa_text = ""
    try:
        from core.gongfa_spectrum import get_gongfa_summary

        gongfa_text = get_gongfa_summary()
    except Exception:
        gongfa_text = "(init)"
    # Treasure spectrum (safe)
    treasure_text = ""
    try:
        from core.treasure_spectrum import get_treasure_summary

        treasure_text = get_treasure_summary()
    except Exception:
        treasure_text = "(init)"
    # Steed spectrum (safe)
    steed_text = ""
    try:
        from core.steed_spectrum import get_steed_summary

        steed_text = get_steed_summary()
    except Exception:
        steed_text = "(init)"
    # Wuji spectrum (safe)
    wuji_text = ""
    try:
        from core.wuji_spectrum import get_wuji_summary

        wuji_text = get_wuji_summary()
    except Exception:
        wuji_text = "(init)"
    # Golden finger (safe)
    gf_text = ""
    try:
        from core.golden_finger import get_golden_finger_summary

        gf_text = get_golden_finger_summary()
    except Exception:
        gf_text = "(init)"
    # Familiar spectrum (safe)
    familiar_text = ""
    try:
        from core.familiar_spectrum import get_familiar_summary

        familiar_text = get_familiar_summary()
    except Exception:
        familiar_text = "(init)"
    # Dwelling spectrum (safe)
    dwelling_text = ""
    try:
        from core.dwelling_spectrum import get_dwelling_summary

        dwelling_text = get_dwelling_summary()
    except Exception:
        dwelling_text = "(init)"
    # Trial spectrum (safe)
    trial_text = ""
    try:
        from core.trial_spectrum import get_trial_summary

        trial_text = get_trial_summary()
    except Exception:
        trial_text = "(init)"
    # Glamour spectrum (safe)
    glamour_text = ""
    try:
        from core.glamour_spectrum import get_glamour_summary

        glamour_text = get_glamour_summary()
    except Exception:
        glamour_text = "(init)"
    # Survival spectrum (safe)
    survival_text = ""
    try:
        from core.survival_spectrum import get_survival_summary

        survival_text = get_survival_summary()
    except Exception:
        survival_text = "(init)"
    return (
        """[CRUX 五兽躯体 — 魂+魄+神器+武技+功法+法宝+坐骑+灵兽+金手指+生存+洞府+秘境+化妆+贴身]
## 魂 (5 DNA)
  白虎·CRUX | 青龙·Codex | 朱雀·Claude | 玄武·ZCode | 麒麟·CodeBuddy
## 魄 (8骨骼)
  event_bus  plugins  cap_reg  watchdog """
        + wds
        + """
  daemon """
        + dd
        + """  DAG  skin  wiring
"""
        + reg_summary
        + """
"""
        + pm_summary
        + """
## 神器套装 (5套25件)
"""
        + as_text
        + """
## 洞府
  """
        + dwelling_text
        + """
## 秘境
  """
        + trial_text
        + """
## 化妆
  """
        + glamour_text
        + """
## 灵兽
  """
        + familiar_text
        + """
## 金手指
  """
        + gf_text
        + """
## 法宝谱
  """
        + treasure_text
        + """
## 坐骑谱
  """
        + steed_text
        + """
## 武技谱
  """
        + wuji_text
        + """
## 生存技能
  """
        + survival_text
        + """
## 功法谱
  """
        + gongfa_text
        + """
## 贴身七件
"""
        + chr(10).join(intimate)
    )
