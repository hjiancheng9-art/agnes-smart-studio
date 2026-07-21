"""send_stream 核心实现 — 从 ChatSession 提取为模块级生成器函数。

使用与 chat_tool_dispatch.py / chat_vision.py 相同的函数注入模式：
- 模块级函数接受 `self` 作为第一参数（duck-typing，不标注 ChatSession）
- chat.py 底部注入：ChatSession.send_stream = _send_stream_impl
- 避免循环导入
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.unicode_safety import InvalidUnicodePayloadError


def _send_stream_impl(self, user_text: str, image_url: str | None = None):
    """发送用户消息，流式 yield (kind, payload) 元组。

    Pipeline stages: accepted → plan → context → model → tools → finalize
    """
    self._last_user_text = user_text
    self._last_turn_had_errors = False

    # ── 输入截断: 超长文本存临时文件，避免炸上下文 ──
    _MAX_INPUT_CHARS = 4000
    _input_len = len(user_text)
    if _input_len > _MAX_INPUT_CHARS:
        import tempfile

        tmp_dir = tempfile.gettempdir()
        tmp_path = f"{tmp_dir}/crux_input_{os.getpid()}.txt".replace("\\", "/")
        with open(tmp_path, "w", encoding="utf-8") as f_tmp:
            f_tmp.write(self._last_user_text)
        self._temp_input_files.add(tmp_path)
        import atexit

        atexit.register(lambda p=tmp_path: os.path.exists(p) and os.remove(p))  # final safety net
        user_text = (
            f"[大文本 {_input_len} 字符，完整内容: {tmp_path}]\n"
            f"开头:\n{user_text[: _MAX_INPUT_CHARS // 2]}\n"
            f"...\n结尾:\n{user_text[-_MAX_INPUT_CHARS // 4 :]}"
        )
        yield ("info", f"输入过长({_input_len}字符)，已截断。用 read_file 读完整内容: {tmp_path}")

    # 触发 CHAT_TURN_START 钩子
    try:
        from core.hooks import HookType
        from core.hooks import fire as _fire_hook

        _fire_hook(HookType.CHAT_TURN_START, prompt=user_text)
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass

    # #6 预算守卫：会话开始时检查今日花费，超限/接近上限仅提示不阻断
    try:
        from core.cost_tracker import check_budget

        warning = check_budget()
        if warning:
            yield ("info", warning)
    except (ImportError, OSError) as e:
        logger.debug("cost_tracker.check_budget failed: %s: %s", type(e).__name__, e)
    except Exception as e:
        logger.debug("cost_tracker.check_budget unexpected error: %s: %s", type(e).__name__, e)

    # ── 方法论分级：根据意图自动判定 A/B/C/D 任务等级 ──
    try:
        try:
            from core.methodology import get_methodology_state

            get_methodology_state().record_step()
        except (ImportError, OSError):
            pass
    except (ImportError, OSError) as e:
        logger.debug("optional module skipped: %s", e)

        pass

    # ── 多模态分支：有图片 → vision 模型理解 + LLM 推理 ──
    if image_url:
        try:
            vision_raw = self._vision_fallback(user_text, image_url)
        except Exception as e:
            logger.exception("Vision fallback crashed unexpectedly")
            vision_raw = f"(视觉理解异常: {type(e).__name__}: {e})"
        # 注册到视觉上下文（持久化图片 + 原始描述，供后续追问重查）
        self.vision_ctx.register(image_url, vision_raw)
        # 将 vision 输出作为"系统视觉情报"注入用户消息，替换原始图片 URL
        # Truncate to prevent context window waste (complex mode: 4096 tokens max)
        _MAX_VISION_CHARS = 2000
        _clean = vision_raw[: _MAX_VISION_CHARS * 2]  # ~4000 chars ≈ 1000 tokens
        # Strip magic tokens that could confuse the downstream LLM
        for _tok in ("<|im_end|>", "<|im_start|>", "<|user|>", "<|assistant|>", "<|system|>"):
            _clean = _clean.replace(_tok, "")
        user_text = f"[图片分析] {_clean}\n\n用户提问: {user_text}"
        # 不 return，继续走正常 LLM 流式推理

    # ── Unified execution plan ──
    try:
        from core.runtime_types import ExecutionMode, TaskComplexity, plan_from_policy

        _plan = plan_from_policy(user_text)

        # Yield planning info for non-trivial tasks
        if _plan.complexity >= TaskComplexity.STANDARD:
            yield ("info", "【分析】任务分析中...")

        # For orchestrate/swarm: trigger directly instead of asking the model
        # to produce a tool call. This is NOT a workaround — it's the correct
        # architecture for deterministic workflows.
        _self_heal_requested = any(kw in user_text.lower() for kw in ("自检", "自修", "自愈", "self_heal", "self heal"))
        _skip_orch = len(user_text) < 60 and ("?" in user_text or "？" in user_text)
        if (
            _plan is not None
            and _plan.mode in (ExecutionMode.ORCHESTRATE, ExecutionMode.SWARM)
            and _self_heal_requested
            and not _skip_orch
        ):
            import time as _time

            # Append user message to history (same as normal path)
            self.messages.append({"role": "user", "content": user_text})
            yield ("stream_start", {"run_id": str(uuid.uuid4())[:12], "message": "start"})

            yield ("info", "【编排】自检自修 — 完整执行")
            _result_parts = []
            _t0 = _time.monotonic()

            # Step 1: self_heal — full audit + auto-fix
            yield ("info", "[1/3] self_heal 全量审计 + 自动修复...")
            try:
                _raw1, _ = self._dispatch_tool("self_heal", '{"fix":true,"full":true}')
                _result_parts.append(f"## 自愈审计\n{str(_raw1)[:2000]}")
                yield ("info", f"  自愈完成 ({_time.monotonic() - _t0:.1f}s)")
            except Exception as e:
                _result_parts.append(f"## 自愈失败\n{str(e)[:300]}")
                yield ("error", f"  自愈失败: {e}")

            # Step 2: code_review on changed files
            yield ("info", "[2/4] 代码审查...")
            try:
                _raw2, _ = self._dispatch_tool("code_review", "{}")
                _result_parts.append(f"## 代码审查\n{str(_raw2)[:1500]}")
                yield ("info", f"  审查完成 ({_time.monotonic() - _t0:.1f}s)")
            except Exception as e:
                _result_parts.append(f"## 审查失败\n{str(e)[:300]}")

            # Step 3: lint fix + format
            yield ("info", "[3/4] 代码质量修复...")
            try:
                _raw3a, _ = self._dispatch_tool("run_lint", '{"fix":true}')
                _result_parts.append(f"## Lint\n{str(_raw3a)[:1000]}")
            except Exception as e:
                _result_parts.append(f"## Lint 失败\n{str(e)[:300]}")
            try:
                _raw3b, _ = self._dispatch_tool("run_format", "{}")
                _result_parts.append(f"## 格式化\n{str(_raw3b)[:500]}")
            except Exception as e:
                _result_parts.append(f"## 格式化失败\n{str(e)[:300]}")
            yield ("info", f"  质量修复完成 ({_time.monotonic() - _t0:.1f}s)")

            # Step 4: summary
            _elapsed = _time.monotonic() - _t0
            import re as _re

            _result_text = "\n\n".join(_result_parts)
            _clean = _re.sub(r"\x1b\[[0-9;]*m", "", _result_text)
            _lines = [l for l in _clean.split("\n") if l.strip() and not l.startswith("══")]
            if _lines:
                yield ("info", f"[完成] {_elapsed:.1f}s — {'; '.join(_lines[:3])}")
            if _clean.strip():
                yield ("text", _clean)
            self.messages.append({"role": "assistant", "content": _result_text or ""})
            self._finalize_outcome(self.model, None)
            return

        if _plan.mode != ExecutionMode.DIRECT:
            instruction = "[执行策略] "
            if _plan.mode == ExecutionMode.ORCHESTRATE:
                instruction += (
                    "分步骤完成用户任务：先分析 → 再执行 → 最后验证。不要跳到系统自检，直接做用户要你做的事。"
                )
            elif _plan.mode == ExecutionMode.SWARM:
                instruction += "请使用 `agent_swarm` 并行分派子智能体。"
            original_user = user_text
            user_text = f"{instruction}\n\n用户任务: {original_user}"

        # Auto-upgrade model for complex tasks
        if _plan.complexity >= 3 and ("flash" in self.model or "light" in self.model):
            import re as _re

            pro = _re.sub(r"\b(flash|light)\b", "pro", self.model)
            if pro != self.model:
                self.model = pro
                self.routing.select(self.routing.active_provider, pro)
                yield ("info", f"自动切换模型: {self.model}")
    except ImportError:
        _plan = None

    # ── 项目上下文注入：让模型知道当前项目状态 ──
    try:
        from core.project_context import get_project_snapshot

        ctx = get_project_snapshot()
        if ctx:
            # Inject as system message so model knows project state without user asking
            # Remove previous context injection (replace last system-context if exists)
            self.messages = [m for m in self.messages if not str(m.get("content", "")).startswith("[项目状态]")]
            self.messages.insert(1, {"role": "system", "content": ctx})
            # ── Methodology: context collected (step 2) ──
            try:
                from core.methodology import get_methodology_state

                get_methodology_state().advance_workflow("context_collected")
            except ImportError:
                pass
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)

    # ── 纯文本分支：加 user message ──
    self.messages.append({"role": "user", "content": user_text})

    import time as _time

    _turn_start = _time.monotonic()  # track turn start for heartbeat timing

    # Auto-route: classify prompt intent → dynamically switch model tier
    # (e.g. complex code → pro, simple Q&A → light, deep reasoning → reasoner)
    self._auto_route(user_text)

    # ── Lightweight pre-flight: only what's needed for routing ──
    try:
        intel_analysis = self._intelligence_hook.analyze(user_text)
        self._intel_mode = intel_analysis.get("mode", "BALANCED")
    except Exception:
        self._intel_mode = "BALANCED"

    try:
        from core.multi_agent import compute_agent_mode

        _agent_mode, _agent_score, _agent_breakdown = compute_agent_mode(user_text, {})
        self._last_agent_score = _agent_score
        self._last_agent_mode = _agent_mode.value
    except (ImportError, OSError):
        pass

    # 3. Pipeline 执行: DEEP/SAFE 模式跑 Plan→Critic→Repair 工作流
    # 已禁用 — 后台 code_review 增加延迟且 false-positive 过多，干扰任务执行
    if False:  # DEEP/SAFE pipeline disabled (false-positive noise)
        try:
            import asyncio
            import threading

            from core.chat_tool_retry import _PipelineToolbus

            toolbus = _PipelineToolbus(self._dispatch_tool, self.tools)

            # 后台运行 pipeline，不阻塞主回复
            def _run_pipeline():
                try:
                    result = asyncio.run(
                        self._intelligence_hook.execute_pipeline(
                            user_text,
                            context={"project": str(Path(__file__).parent.parent)},
                            toolbus=toolbus,
                        )
                    )
                    self._pipeline_result = result
                except Exception:
                    logger.debug("Exception in chat", exc_info=True)

            # Track pipeline threads — join old ones to prevent accumulation
            if not hasattr(self, "_pipeline_threads"):
                self._pipeline_threads = []
            # Clean up finished threads
            self._pipeline_threads = [t for t in self._pipeline_threads if t.is_alive()]
            t = threading.Thread(target=_run_pipeline, daemon=True, name="crux-pipeline")
            self._pipeline_threads.append(t)
            t.start()
        except Exception as e:
            logger.debug("Pipeline execution skipped: %s", e)

    # Inject relevant past memories as context
    self._inject_memory(user_text)

    # 视觉上下文：后续追问时按需重查 vision 模型
    if not image_url and self.vision_ctx.active and self.vision_ctx.needs_lookup(user_text):
        fresh = self.vision_ctx.reask(
            user_text,
            lambda t, u: self._vision_fallback(t, u),
        )
        if fresh:
            # 用重查结果覆盖最后一条用户消息
            augmented = f"[图片局部查询] {fresh}\n\n用户提问: {user_text}"
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages[-1]["content"] = augmented
            else:
                self.messages.append({"role": "user", "content": augmented})

    # Multi-model deliberation for complex questions
    from core.cognitive_orchestrator import is_complex

    if self._vote_enabled and is_complex(user_text) and not image_url:
        result = self._deliberate(user_text)
        if result and result.get("confidence") in ("high", "medium"):
            content = f"{result['answer']}\n\n[{result['models_used']} models, confidence: {result['confidence']}]"
            if result.get("dissenting") and result["dissenting"] != "none":
                content += f"\n[dim]Dissent: {result['dissenting']}[/]"
            self.messages.append({"role": "assistant", "content": content})
            self._check_budget()
            yield ("text", content)
            return

    # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
    if self.ctx_mgr.needs_compression(self.messages) or len(self.messages) > 40:
        self.messages = self.ctx_mgr.compress(self.messages, self.client, self.model)

    tools = self.tools.get_filtered_definitions(user_text) if self.supports_tools else None
    _active_tool_names: set[str] | None = {d["function"]["name"] for d in tools} if tools else None

    # ── 模型级 fallback 链（对标 Claude fallbackModel）──
    fallback_chain = self._text_fallback_chain()
    fallback_tried = 0

    # ── 预检: 活跃供应商挂了就立刻切 ──
    try:
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        active_pid = mgr.state.active
        if mgr.state.is_down(active_pid) or not mgr.state.circuit_can_try(active_pid):
            if len(fallback_chain) > 1:
                fallback_chain = fallback_chain[1:]
                self.model, self.client = fallback_chain[0]
                yield ("info", f"当前供应商不可用，已切换至 {self.model}")
                self._rebuild_ctx_mgr()
    except (ImportError, OSError) as e:
        logger.debug("provider precheck skipped: %s", e)

    # tool calling 循环（有上限，防止死循环）
    from core.chat import MAX_TOOL_LOOPS

    _base = MAX_TOOL_LOOPS
    _env_override = os.environ.get("CRUX_MAX_TOOL_LOOPS")
    if _env_override:
        try:
            _base = int(_env_override)
        except ValueError:
            logger.warning(
                "CRUX_MAX_TOOL_LOOPS=%r is not a valid integer, using default %d", _env_override, MAX_TOOL_LOOPS
            )
    _effective_max = _base * 2 if getattr(self, "unlimited_tools", False) else _base
    # ── Adaptive limit: expand for plans, shrink on failures ──
    try:
        from core.skill_orchestrator import get_orchestrator

        orch = get_orchestrator()
        if hasattr(orch, "_last_plan") and orch._last_plan and orch._last_plan.steps:
            plan_steps = len(orch._last_plan.steps)
            _effective_max = max(_effective_max, plan_steps * 8)
    except (ImportError, AttributeError):
        pass
    self._consecutive_failures = 0
    self._consecutive_successes = 0
    self._effective_max = _effective_max
    buffer = ""
    _executed_signatures: set[tuple[str, str]] = set()
    _executed_cache: dict[tuple[str, str], str] = {}
    _stream_error_break = False
    _test_run_count = 0

    while fallback_tried < len(fallback_chain):
        _use_model, _use_client = fallback_chain[fallback_tried]
        fallback_tried += 1
        _stream_error_break = False

        for _loop in range(_effective_max):
            buffer, tool_calls = "", []
            _stream_error = False
            _last_usage = None
            try:
                delta_result = yield from self._consume_stream_delta(
                    _use_client,
                    _use_model,
                    tools,
                )
            except InvalidUnicodePayloadError:
                logger.exception(
                    "_consume_stream_delta: payload encoding error — NOT a provider failure, skipping failover"
                )
                yield ("error", "请求数据含非法字符（Unicode surrogate），已跳过。请重试。")
                return
            except Exception as e:
                logger.exception("_consume_stream_delta 异常")
                yield ("error", f"流式接收中断: {type(e).__name__}: {e}")
                _stream_error_break = True
                break
            buffer, tool_calls, _stream_error, _last_usage = delta_result
            # 收完一轮 delta：有 tool_calls → 执行并喂回，进入下一轮
            if tool_calls:
                buffer = self._append_assistant_with_tools(buffer, tool_calls)
                try:
                    yield from self._run_tool_calls(
                        tool_calls,
                        _executed_signatures,
                        _executed_cache,
                        _loop,
                    )
                except Exception as e:
                    logger.exception("_run_tool_calls 异常")
                    yield ("error", f"工具执行中断: {type(e).__name__}: {e}")
                    _stream_error_break = False
                    break
                # Grow the visible tool set with any tools the model just called
                if _active_tool_names is not None and tool_calls:
                    for _tc in tool_calls:
                        _fn = _tc.get("function", {}) if isinstance(_tc, dict) else {}
                        _name = _fn.get("name")
                        if _name:
                            _active_tool_names.add(_name)
                    tools = self.tools.get_definitions_for_names(_active_tool_names)
                # Detect fix-test-fail-fix runaway loops
                _test_tools = sum(
                    1 for tc in tool_calls if isinstance(tc, dict) and tc.get("function", {}).get("name") == "run_test"
                )
                if _test_tools:
                    _test_run_count += _test_tools
                if _test_run_count > 5:
                    yield ("info", f"测试已运行 {_test_run_count} 次，疑似死循环。已自动停止。")
                    self.messages.append({"role": "assistant", "content": buffer})
                    self._finalize_outcome(_use_model, _last_usage)
                    return
                continue

            # 无 tool_calls：检查是否流错误（需 fallback）还是正常收尾
            if _stream_error or self._is_stream_error(buffer):
                if _loop == 0 and fallback_tried < len(fallback_chain):
                    try:
                        mgr = get_provider_manager()
                        new_client, new_pid = mgr.handle_failure(mgr.state.active, 500)
                        if new_client:
                            self.client = new_client
                            self._current_provider = new_pid
                            mgr.state.record_success(new_pid)
                            logger.info("failover: -> %s (auto)", new_pid)
                            yield ("info", f"Provider 自动切换: {new_pid}")
                        else:
                            mgr.state.mark_down(mgr.state.active)
                    except Exception as e:
                        logging.debug("Failed to mark provider down: %s", str(e)[:120])
                    yield ("info", f"模型 {_use_model} 连接中断，尝试 fallback...")
                    from core.observability import metrics

                    metrics.increment("fallback.text_model")
                    _stream_error_break = True
                    break
                self.messages.append({"role": "assistant", "content": buffer})
                return

            # 正常收尾 — 检测空响应，若是则触发重试
            _empty_buffer = not buffer or not buffer.strip()
            if _empty_buffer and _loop == 0:
                yield ("info", "模型返回空内容，正在重试…")
                try:
                    retry_delta = yield from self._consume_stream_delta(
                        _use_client, _use_model, tools, _retry_empty=True
                    )
                    retry_buffer, _, _, retry_usage = retry_delta
                    if retry_buffer and retry_buffer.strip():
                        buffer = retry_buffer
                        if retry_usage:
                            _last_usage = retry_usage
                        _empty_buffer = False
                        yield ("info", "重试成功")
                except Exception as e:
                    logger.debug("empty-retry failed: %s", e)
            if _empty_buffer:
                buffer = "（模型未返回内容，请重试或换一种表述）"
                yield ("text", buffer)
            self._finalize_outcome(_use_model, _last_usage)
            self.messages.append({"role": "assistant", "content": buffer})
            # ── 红旗警示: 检测输出中的危险短语 ──
            try:
                from core.methodology import detect_red_flags, get_methodology_state

                flags = detect_red_flags(buffer)
                if flags:
                    for w in flags:
                        yield ("info", w)
                    get_methodology_state().advance_workflow("verified")
            except (ImportError, OSError) as e:
                logger.debug("optional module skipped: %s", e)

                pass
            if (yield from self._try_adversarial_bypass(buffer, user_text, _use_client, _use_model, tools)):
                return
            # ── Pipeline 结果: 后台运行完成后 yield ──
            _pr = getattr(self, "_pipeline_result", None)
            if _pr:
                with self._pipeline_lock:
                    _pr = self._pipeline_result
                    if _pr:
                        if _pr.get("passed") is False:
                            yield ("info", f"[Pipeline] 审查未通过: {_pr.get('summary', '')[:200]}")
                        elif _pr.get("summary"):
                            yield ("info", f"[Pipeline] {_pr.get('summary', '')[:200]}")
                        self._pipeline_result = None
            self._trigger_reflection()
            self._auto_remember()
            return

    # for _loop 结束：区分两种情况
    if not _stream_error_break:
        yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
        self._record_trace_failure(f"tool loop overflow: {_effective_max} rounds", step_name="tool_loop")
        self.messages.append({"role": "assistant", "content": buffer})
        self._check_budget()
        self._record_outcome_promptlab()
        return

    # All fallback models exhausted — tell the user something went wrong.
    tried = ", ".join(m for m, _ in fallback_chain)
    self._record_trace_failure(f"all models exhausted: {tried}", step_name="fallback_chain")
    yield ("error", f"所有模型均不可用（已尝试: {tried}），请稍后重试或 /provider 切换")
