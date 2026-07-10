"""Tool dispatch implementation — extracted from chat.py.

Contains _dispatch_tool_impl: executes tool calls with permission checks,
hook integration, TRM routing, and adversarial bypass fallback.
Injected into ChatSession at module level for circular import safety.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("crux.tool_dispatch")


def _dispatch_tool_impl(self, name: str, args_json: str, *, confirmed: bool = False) -> tuple[str, list[tuple]]:
    """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

    副作用列表元素: ("info", str) / ("image", dict) / ("video", dict) / ("confirm", dict)

    与命令式路径对齐：均经过 SmartBrain Prompt 增强后再调引擎。
    支持生命周期 hook（PRE_TOOL_USE / POST_TOOL_USE）和高风险工具确认。

    Args:
        confirmed: 若 True，跳过高风险工具确认检查（用户已在 UI 层确认）。
            由 _run_tool_calls 在 confirm 通过后二次调用时传入。
    """
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        args = {}

    # ── cdp_ask_chatgpt 参数归一化（第二层防护） ──
    if name == "cdp_ask_chatgpt":
        from core.tool_call_validator import _normalize_chatgpt_args
        args = _normalize_chatgpt_args(args)

    # trace 上下文由 multi_agent contextvar 自动传播
    if not confirmed:
        from core.permission import get_permission_manager

        pm = get_permission_manager()
        if pm.needs_confirmation(name, args):
            confirm_data = {"tool": name, "args": args, "mode": pm.get_mode_name()}
            return ("", [("confirm", confirm_data)])
    try:
        from core.hooks import HookType, hook_manager

        pre_evt = hook_manager.fire(HookType.PRE_TOOL_USE, data={"tool_name": name, "args": args})
        if pre_evt.stop_processing:
            return ("工具调用被拦截（PRE_TOOL_USE hook）", [])
    except (ImportError, OSError):
        pass
    prompt = args.get("prompt", "")
    image_url = args.get("image_url", "") or args.get("image", "")
    image_urls = args.get("image_urls", []) or []
    mode = args.get("mode", "")
    if name == "generate_image":
        size = args.get("size", "1024x768")
        # seed 固定：未指定时随机生成，确保可复现
        import random as _rnd
        seed = args.get("seed") or _rnd.randint(0, 2147483647)
        system = args.get("system")
        neg_from_args = args.get("negative_prompt")
        image_url = args.get("image_url")
        image_urls = args.get("image_urls")
        mode = args.get("mode", "text2image")

        # 归一化：image_url → image_urls；冲突则报错
        if image_url and image_urls and image_url not in image_urls:
            return ("图片参数错误: image_url 和 image_urls 冲突", [])
        if image_url and not image_urls:
            image_urls = [image_url]

        side: list[tuple[str, str | dict]] = [("info", f"生成图片: {args.get('prompt','')[:50]}...")]

        try:
            prompt = args.get("prompt", "")
            fp = prompt
            neg = neg_from_args

            try:
                r = self.brain.enhance_image_prompt(prompt)
                fp = r.get("optimized_prompt", prompt)
                neg = neg or r.get("negative_prompt", "") or None
            except Exception as e:
                logger.debug("brain.enhance_image_prompt failed: %s", e)

            if system:
                fp = f"[{system}] {fp}"

            from core.providers.agnes import AgnesProvider
            agnes = AgnesProvider()
            result = agnes.generate_image(
                prompt=fp, size=size, seed=seed, negative_prompt=neg,
                image_urls=image_urls,
            )
            agnes.close()
            url = result.get("url", "")

            if not url:
                data = self.t2i.generate(prompt=fp, size=size, seed=seed)
                url = data.get("url", "")

            side.append(("image", {"url": url}))
            side.append(("info", f"图片已生成: {url[:60]}..."))

            try:
                from core.cost_tracker import record_usage
                record_usage(model="agnes-image-2.1-flash", kind="image", label="generate_image", call_count=1)
            except Exception:
                import logging
                logging.getLogger('crux').debug('silent except', exc_info=True)

            return (f"图片已生成: {url}", side)

        except Exception as e:
            return (f"图片生成失败: {e}", side)
    if name == "generate_video":
        size_str = args.get("size", "1152x768")
        num_frames = args.get("num_frames", 121)
        import random as _rnd2
        seed = args.get("seed") or _rnd2.randint(0, 2147483647)
        system = args.get("system")
        neg_from_args = args.get("negative_prompt")
        image_url = args.get("image_url")
        image_urls = args.get("image_urls")
        mode = args.get("mode", "text2video")
        prompt = args.get("prompt", "")

        # 互斥校验：image_url 和 image_urls 不能同时为不同值
        if image_url and image_urls and image_url not in image_urls:
            return ("视频参数错误: image_url 和 image_urls 冲突，请只使用其中一个", side)

        # 归一化：image_urls 只有1张图 → 降级为单图 image_url
        if image_urls and len(image_urls) == 1 and not image_url:
            image_url = image_urls[0]
            image_urls = None

        # duration（秒）→ num_frames 映射（优先，覆盖 num_frames）
        duration = args.get("duration")
        if duration:
            duration_map = {2: 57, 3: 81, 4: 97, 5: 121, 6: 145, 8: 193, 10: 241, 12: 289, 15: 361, 18: 441}
            num_frames = duration_map.get(duration, num_frames)

        side: list[tuple[str, str | dict]] = [("info", f"正在生成视频（可能需几分钟）: {prompt}")]
        if duration:
            side.append(("info", f"⏱ 时长 {duration}s → {num_frames} 帧 @24fps"))

        try:
            fp = prompt
            neg = neg_from_args

            # P1: ShotContract — 强制一镜一动作
            from core.creative.shot_contract import compile_shot, validate_single_action
            is_valid, val_msg = validate_single_action(prompt)
            if not is_valid:
                return (f"视频生成被拒绝: {val_msg}\n请拆分为独立镜头，每个镜头只包含一个动作", side)

            contract = compile_shot(prompt, num_frames=num_frames, seed=seed)
            fp = contract.optimized_prompt

            # I2V 引导：有参考图时自动切换 prompt 策略
            if image_urls or image_url:
                fp = (
                    f"[I2V] Reference image defines identity/composition/style/first-frame. "
                    f"Describe ONLY: ONE action, ONE camera movement, lighting changes, ending state. "
                    f"Keep stable: composition, subject, style. "
                    f"DO NOT repeat what reference already shows. | {fp}"
                )

            # P1: SmartBrain 增强
            try:
                r = self.brain.enhance_video_prompt(prompt)
                enhanced = r.get("optimized_prompt", "")
                if enhanced:
                    fp = enhanced
                neg = neg or r.get("negative_prompt", "") or None
            except Exception as e:
                logger.debug("brain.enhance_video_prompt failed: %s", e)

            if system:
                fp = f"[{system}] {fp}"

            frame_rate = args.get("frame_rate", 24)

            # P1: RPM 限流 — 视频 1 RPM
            from core.creative.rpm_limiter import RPMLimiter
            limiter = RPMLimiter()
            side.append(("info", "等待视频生成队列..."))
            acquired = limiter.wait("video", timeout=120.0)
            if not acquired:
                return ("视频队列等待超时，请稍后再试", side)

            # P1: 首帧 QC — 文生视频时才做
            if not image_url and not image_urls:
                try:
                    from core.providers.agnes import AgnesProvider
                    agnes = AgnesProvider()
                    # 先生成首帧
                    frame_result = agnes.generate_image(
                        prompt=fp,
                        size=size_str,
                        seed=seed,
                        negative_prompt=neg,
                    )
                    frame_url = frame_result.get("url", "")
                    if frame_url:
                        side.append(("info", "首帧已生成，进行 QC 检查..."))
                        # QC 检查
                        from core.creative.qc import FrameQC
                        qc = FrameQC(threshold=60)
                        qc_result = qc.check(frame_url, fp)
                        side.append(("info", f"首帧 QC: {qc_result.score}/100 {'通过' if qc_result.passed else '未通过'}"))
                        if not qc_result.passed:
                            agnes.close()
                            issues = ", ".join(qc_result.issues[:3])
                            return (f"首帧 QC 未通过 (score={qc_result.score}/100): {issues}\n请优化提示词后重试", side)
                    agnes.close()
                except Exception as e:
                    logger.debug("首帧 QC 失败（不阻塞视频生成）: %s", e)

            # 使用 AgnesProvider 提交视频任务
            from core.providers.agnes import AgnesProvider
            agnes = AgnesProvider()

            task = agnes.create_video_task(
                prompt=fp,
                size=size_str,
                num_frames=num_frames,
                frame_rate=frame_rate,
                seed=seed,
                negative_prompt=neg,
                image_url=image_url,
                image_urls=image_urls,
                mode=mode,
            )

            video_id = task.get("video_id", "")

            if not video_id:
                agnes.close()
                return ("视频提交失败: 未获取到 video_id", side)

            side.append(("info", f"视频任务已提交，video_id={video_id}"))

            # 等待完成（最多 2 分钟）
            import threading
            result_holder = {"result": None}

            def poll_worker():
                result_holder["result"] = agnes.wait_for_video(
                    video_id=video_id,
                    poll_interval=3.0,
                    max_wait=120.0,
                )

            t = threading.Thread(target=poll_worker, daemon=True)
            t.start()
            t.join(timeout=2.0)

            agnes.close()

            if t.is_alive():
                return (f"视频生成中（请稍后用 video_id={video_id} 查询状态）", side)
            else:
                result = result_holder["result"]
                if result and result.get("status") in ("completed", "SUCCESS", "done"):
                    local_path = result.get("local_path", "")
                    url = result.get("url", "")
                    side.append(("video", {"url": url or "", "local_path": local_path}))
                    return (f"视频已生成 [video_id={video_id}]: {local_path or url}", side)
                elif result and result.get("status") in ("failed", "FAILED", "error"):
                    return (f"视频生成失败: {result.get('error', 'unknown')}", side)
                else:
                    return (f"视频生成中（进度 {result.get('progress', 0):.0f}%），video_id={video_id}", side)

        except Exception as e:
            return (f"视频生成失败: {e}", side)
    if name == "multi_agent":
        goal = args.get("goal", "")
        side: list[tuple[str, str | dict]] = [("info", f"正在启动多智能体协调: {goal}")]
        try:
            from core.multi_agent import coordinate

            def _tool_exec(tool, tool_args):
                if self.tools.has(tool):
                    return self.tools.execute(tool, tool_args)
                return f"[multi_agent] 工具 {tool} 不可用"

            result = coordinate(goal, _tool_exec)
            tasks_done = result.get("tasks_done", 0)
            tasks_total = result.get("tasks_total", 0)
            tasks_failed = result.get("tasks_failed", 0)
            elapsed = result.get("elapsed", "?")
            summary = (
                f"多智能体协调完成: {tasks_done}/{tasks_total} 任务成功, 耗时 {elapsed}s"
            )
            if tasks_failed:
                summary += f", {tasks_failed} 失败"
            return (summary, side)
        except (RuntimeError, OSError, ValueError) as e:
            return (f"多智能体协调失败: {e}", side)
    if name == "trm_tune":
        try:
            from core.growth_engine import get_growth_engine

            ge = get_growth_engine()
            do_apply = args.get("apply", False)
            result = ge.auto_tune(apply=do_apply)
            bottlenecks = ge.detect_bottlenecks()
            suggestions = ge.suggest_improvements()
            lines = ["CRUX Self-Optimization Results", "=" * 40]
            lines.append(f"Total calls analyzed: {ge._total_calls_ever}")
            if result.get("applied"):
                applied = result.get("applied", [])
                lines.append(f"\nApplied changes ({len(applied)}):")
                for change in applied:
                    lines.append(f"  + {change.get('action', '?')}: {change.get('intent', '')}/{change.get('tool', '')}")
                    if "new_order" in change:
                        lines.append(f"    -> {' > '.join(change['new_order'])}")
            if not do_apply:
                lines.append("\n[Dry run — use apply=true to commit changes]")
            if bottlenecks:
                lines.append(f"\nBottlenecks ({len(bottlenecks)}):")
                for b in bottlenecks[:3]:
                    sev = b.get("severity", "?")
                    intent = b.get("intent", "?")
                    tool = b.get("tool", "?")
                    reasons = b.get("reasons", [])
                    lines.append(f"  ! [{sev}] {intent}/{tool}: {', '.join(reasons)}")
            if suggestions:
                lines.append("\nSuggestions:")
                for s in suggestions:
                    lines.append(f"  ? {s}")
            return ("\n".join(lines), [])
        except Exception as e:
            logger.debug("error in except: %s", e, exc_info=True)
            return (f"Auto-tune error: {e}", [])
    if name == "trm_growth":
        try:
            from core.growth_engine import get_growth_engine

            ge = get_growth_engine()
            if args.get("reset"):
                ge.reset()
                return ("Growth data reset.", [])
            intent_filter = args.get("intent", "")
            if intent_filter and intent_filter in ge.intents:
                is_ = ge.intents[intent_filter]
                lines = [f"Growth — [{intent_filter}] ({is_.total_calls} calls)"]
                for ts in is_.ordered_tools:
                    status = "D" if ts.demoted else "✓"
                    lines.append(
                        f"  {status} {ts.tool}: {ts.success_rate:.0%} success, {ts.avg_latency_ms:.0f}ms avg, {ts.calls} calls"
                        + (f" (CF:{ts.consecutive_failures})" if ts.consecutive_failures else "")
                    )
                return ("\n".join(lines), [])
            return (ge.get_summary(), [])
        except Exception as e:
            logger.debug("error in except: %s", e, exc_info=True)
            return (f"Growth engine error: {e}", [])
    if name == "trm_catalog":
        try:
            from core.tool_registry_mesh import CATEGORY_META, get_trm

            trm = get_trm()
            trm.discover_all(timeout=5.0)
            cat_filter = args.get("category", "")
            src_filter = args.get("source", "")
            tools_found = trm.find(category=cat_filter, source=src_filter)
            lines = [
                f"TRM Catalog — {len(tools_found)} tools",
                f"Sources: {trm.sources}",
                f"Categories: {trm.categories}",
            ]
            for intent, meta in sorted(CATEGORY_META.items()):
                available = [t for t in meta["order"] if t in trm._tools or "*" in t]
                lines.append(f"\n  [{intent}] {meta['desc']}")
                lines.append(f"    路由: {(' → '.join(available) if available else '(none)')}")
            lines.append("\n--- Tools ---")
            for t in sorted(tools_found, key=lambda x: (x.category, x.name)):
                desc = t.description[:80].replace("\n", " ")
                lines.append(f"  [{t.category}] {t.name} ({t.source}) — {desc}")
            return ("\n".join(lines), [])
        except Exception as e:
            logger.debug("error in except: %s", e, exc_info=True)
            return (f"TRM catalog error: {e}", [])
    if name == "trm_route":
        intent = args.get("intent", "")
        if not intent:
            return ("trm_route requires 'intent' parameter (search/review/execute/think/generate/status)", [])
        try:
            from core.tool_registry_mesh import get_trm

            trm = get_trm()
            trm.discover_all(timeout=5.0)
            route_kwargs = {}
            if args.get("query"):
                route_kwargs["query"] = args["query"]
            if args.get("prompt"):
                route_kwargs["prompt"] = args["prompt"]
            if args.get("target"):
                route_kwargs["target"] = args["target"]
            if args.get("plan"):
                route_kwargs["prompt"] = args["plan"]
            if args.get("work_dir"):
                route_kwargs["work_dir"] = args["work_dir"]
            if args.get("timeout"):
                route_kwargs["timeout"] = args["timeout"]
            if not route_kwargs:
                route_kwargs["prompt"] = args.get("query") or args.get("prompt") or intent
            result = trm.route(intent, **route_kwargs)
            summary = f"TRM Route [{intent}] → {result.tool} ({result.source}) [{('fallback' if result.fallback_used else 'primary')}] ({result.latency_ms:.0f}ms)\n"
            if result.error:
                summary += f"Error: {result.error}\n"
            if result.result:
                summary += f"Result: {json.dumps(result.result, ensure_ascii=False, default=str)[:2000]}"
            return (summary, [("info", f"Routed to {result.tool}")])
        except Exception as e:
            logger.debug("error in except: %s", e, exc_info=True)
            return (f"TRM route error: {e}", [])
    # P0: Generation tool guard — image/video must NEVER fall through to chat executor
    _GEN_TOOLS = frozenset({"generate_image", "generate_video"})
    if name in _GEN_TOOLS:
        return (f"[路由错误] {name} 是专用生成工具，必须由 dispatch 直接处理，不走通用执行器。请检查 _dispatch_tool_impl 的处理顺序。", [])

    if self.tools.has(name):
        from core.constraints import LONG_RUNNING_TOOLS

        _LONG_RUNNING = LONG_RUNNING_TOOLS
        side: list[tuple[str, str | dict]] = []
        if name in _LONG_RUNNING:
            side.append(("info", f"正在执行 {name}..."))
        result = self.tools.execute(name, args)
        try:
            from core.hooks import HookType, hook_manager

            is_error = isinstance(result, str) and result.startswith("[错误]")
            post_evt = hook_manager.fire(
                HookType.POST_TOOL_USE, data={"tool_name": name, "args": args, "result": result, "error": is_error}
            )
            if isinstance(post_evt.result, str) and post_evt.result:
                result = post_evt.result
        except (ImportError, OSError):
            logger.debug("spectrum module not available")
        side.append(("info", f"工具 {name} 执行完成"))
        return (result, side)
    return (f"未知工具: {name}", [])
