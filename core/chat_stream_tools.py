"""工具执行循环 — 从 ChatSession._run_tool_calls 提取为模块级生成器函数。

使用与 chat_tool_dispatch.py / chat_stream.py 相同的函数注入模式。
"""

from __future__ import annotations

import logging
import time as _time

logger = logging.getLogger(__name__)

from core.chat_tool_helpers import merge_tool_calls
from core.chat_tool_helpers import normalize_tool_args as _normalize_tool_args
from core.chat_tool_retry import auto_retry_tool, format_tool_error
from core.observability import TraceContext, metrics


def _summarize_tool_output(raw: str, tool_name: str = "") -> str:
    """Smart truncation for large tool outputs — keep useful info, drop noise."""
    if not raw or len(raw) <= 2000:
        return raw
    lines = raw.split("\n")
    err_lines = [
        l
        for l in lines
        if any(kw in l.lower() for kw in ("error", "fail", "traceback", "assert", "exception", "warning"))
    ]
    if err_lines:
        head = "\n".join(lines[:5])
        errs = "\n".join(err_lines[:8])
        return f"{head}\n\n... [{len(lines)} lines, {len(err_lines)} flagged]\n\n{errs}"
    head = "\n".join(lines[:6])
    tail = "\n".join(lines[-3:]) if len(lines) > 15 else ""
    return f"{head}\n... [{len(lines) - 9} lines omitted]...\n{tail}" if tail else head


def _run_tool_calls_impl(self, tool_calls, executed_sigs, executed_cache, loop_idx=0):
    """执行并喂回一轮工具调用，yield 副作用，return True 表示应中断流。

    契约（输出不重复 DNA · 工具副作用层）：
    - 配合 merge_tool_calls 的单轮内去重，本方法做**跨轮**去重：
      相同 (name, normalized_args) 的非写工具只执行一次，复用缓存。
    - 写操作类工具（_WRITE_TOOLS）不缓存。
    - yield 用户可见的副作用（info/image/video/confirm）。

    Returns (via StopIteration.value):
        False — confirm 不再中断流（拒绝时占位已在历史中，合法）。
    """
    from core.context_tools import compress_tool_result

    # ── Adaptive state shared with send_stream ──
    _loop = loop_idx

    # ── Methodology fallback gate (defense in depth) ──
    # The PRE_TOOL_USE hook is the primary enforcement. This is a safety net
    # that activates if the hook registration failed silently.
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        fname = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")
        # Normalize: LLM may return args as int/str/list, always pass as string
        if isinstance(raw_args, str):
            try:
                import json as _json

                args = _json.loads(raw_args)
            except (_json.JSONDecodeError, ValueError):
                args = raw_args
        else:
            args = str(raw_args) if raw_args is not None else "{}"
        try:
            from core.methodology import methodology_pre_check

            allowed, reason = methodology_pre_check(fname, args)
            if not allowed:
                yield ("info", f"🚫 方法论阻止: {reason}")
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": f"[Blocked by methodology] {reason}",
                    }
                )
                return False
        except ImportError:
            pass  # methodology module not available — no enforcement

    # ── Phase 1: Tool call validation ──
    if getattr(self, "tvl", None) is not None:
        validation_issues: list[str] = []
        _merged_check = getattr(self, "_last_merged_tool_calls", merge_tool_calls(tool_calls))
        _v_start = _time.time()
        for tc_check in _merged_check:
            fname_c = self.tools.resolve_name(tc_check["function"]["name"])
            fargs_raw = tc_check["function"].get("arguments", "{}")
            if isinstance(fargs_raw, str):
                try:
                    fargs_c = _json.loads(fargs_raw)
                except _json.JSONDecodeError:
                    fargs_c = {}
            else:
                fargs_c = fargs_raw
            issues = self.tvl.validate_tool_call(fname_c, fargs_c)
            if issues:
                for iss in issues:
                    validation_issues.append(f"[{iss.code.value}] {iss.tool_name}: {iss.message}")
        _v_duration = (_time.time() - _v_start) * 1000
        if validation_issues:
            error_text = "\\n".join(validation_issues)
            logger.warning(f"Tool validation failed:\\n{error_text}")
            yield ("validation_error", error_text)
            msg = f"[ToolCall Validation Failed]\\n{error_text}\\n---\\nFix your tool calls and retry."
            self.messages.append({"role": "tool", "content": msg, "tool_call_id": "__validation__"})
            # Telemetry: validation blocked
            try:
                self.tvl.record_telemetry("tool_validation", "p1", "", _v_duration, False, error_text[:100])
            except Exception:
                logging.getLogger(__name__).debug("silent except", exc_info=True)
            return False
        # Telemetry: validation passed
        try:
            self.tvl.record_telemetry("tool_validation", "p1", "", _v_duration, True, f"{len(_merged_check)} calls OK")
        except Exception:
            logging.getLogger(__name__).debug("silent except", exc_info=True)

    merged = getattr(self, "_last_merged_tool_calls", merge_tool_calls(tool_calls))
    for tc in merged:
        fname = self.tools.resolve_name(tc["function"]["name"])
        fargs = tc["function"].get("arguments", "{}")
        sig = (fname, _normalize_tool_args(fargs))
        # 跨轮去重：非写工具且本会话已执行过 → 复用缓存，不重复 dispatch
        if fname not in self._WRITE_TOOLS and sig in executed_sigs:
            tool_result = executed_cache.get(sig, "")
            # 不 yield 副作用（用户已见过一次）
            append_tool_result = True
        else:
            # Surface tool activity into message pane — compact one-line format
            _desc = {
                "read_file": "读取",
                "write_file": "写入",
                "edit_file": "编辑",
                "run_bash": "执行",
                "run_python": "Python",
                "run_test": "测试",
                "search_files": "搜索",
                "search_symbols": "查符号",
                "git_diff": "diff",
                "git_status": "状态",
                "git_add_commit": "提交",
                "agent_swarm": "并行",
            }.get(fname, fname)
            _path = ""
            if isinstance(fargs, dict):
                _path = str(fargs.get("path", fargs.get("command", "")))[:50]
            elif isinstance(fargs, str):
                _path = fargs[:50]
            _line = f"\n> {_desc} {_path}" if _path else f"\n> {_desc}"
            yield ("text", _line + "\n")
            with TraceContext("tool_call", tool_name=fname, call_id=tc.get("id", "")) as span:
                try:
                    # ── Phase 2c: Diff guard snapshot before write ──
                    if fname in ("write_file", "edit_file", "patch_file"):
                        try:
                            _args2 = _json.loads(fargs) if isinstance(fargs, str) else (fargs or {})
                            _path2 = _args2.get("path", "")
                            if _path2:
                                getattr(self, "tvl", None) and self.tvl.snapshot_before_write(_path2)
                        except Exception:
                            logging.getLogger(__name__).debug("silent except", exc_info=True)

                    # Dispatch (sync, same as HEAD — ThreadPoolExecutor timeout guard
                    # removed because it masked fast-fail errors in mock/test environments
                    # and introduced 120s hangs in fallback paths).
                    raw = self._dispatch_tool(fname, fargs)
                    from core.runtime_result import ToolResult

                    normalized = ToolResult.from_raw(raw)
                    if not normalized.ok:
                        tool_result = format_tool_error(fname, normalized.content)
                    else:
                        content = normalized.content
                        tool_result = _summarize_tool_output(content, fname) if len(content) > 2000 else content
                    side_effects = list(normalized.side_effects)

                    # ── 自动重试: 仅对幂等/可重试工具，且错误表明可修正时才重试 ──
                    from core.chat import _AUTO_RETRY_TOOLS

                    _can_retry = not normalized.ok and fname in _AUTO_RETRY_TOOLS
                    if _can_retry:
                        tool_result, side_effects = auto_retry_tool(self, fname, fargs, tool_result)

                    # ── 工具结果缓存: 缓存成功的只读工具结果 ──
                    try:
                        from core.tool_cache import CACHEABLE_TOOLS, get_tool_cache

                        if fname in CACHEABLE_TOOLS and normalized.ok:
                            get_tool_cache().set(fname, fargs, str(tool_result))
                    except ImportError:
                        pass

                    # ── Phase 2a+b: Validate result + track history ──
                    try:
                        tvl = getattr(self, "tvl", None)
                        if tvl:
                            vr = tvl.validate_result(fname, str(tool_result)[:2000], success=True)
                            if not vr.is_valid:
                                logger.warning(f"Result validation: {fname} -> {len(vr.notes)} issues")
                            tvl.track_tool_use_v2(fname, fargs, str(tool_result)[:2000], success=True)
                    except Exception:
                        logging.getLogger(__name__).debug("silent except", exc_info=True)
                except Exception as e:
                    logger.exception("工具 %s 执行异常", fname)
                    tool_result = f"[错误] 工具 {fname} 执行失败: {type(e).__name__}: {e}"
                    self._record_trace_failure(str(e), step_name=fname)

                    # ── Phase 2a: Track failed execution ──
                    try:
                        tvl = getattr(self, "tvl", None)
                        if tvl:
                            tvl.validate_result(fname, tool_result, success=False)
                            tvl.track_tool_use_v2(fname, fargs, tool_result, success=False)
                    except Exception:
                        logging.getLogger(__name__).debug("silent except", exc_info=True)
                    side_effects = [("info", tool_result)]
                    metrics.increment("tool_errors")
                    self._last_turn_had_errors = True
                # ── Agent mode 反馈: 记录 agent_swarm / multi_agent 执行结果 ──
                if fname in ("agent_swarm", "multi_agent"):
                    try:
                        from core.multi_agent import AgentMode, AgentModeResult, record_agent_mode_result

                        _is_ok = (
                            not str(tool_result).startswith("[错误]") and "error" not in str(tool_result).lower()[:200]
                        )
                        _mode = AgentMode.SWARM if fname == "agent_swarm" else AgentMode.PLAN_EXECUTE
                        _latency = (span.end_time - span.start_time) if hasattr(span, "end_time") else 0.0
                        record_agent_mode_result(
                            AgentModeResult(
                                mode=_mode,
                                task_type="tool_call",
                                success=_is_ok,
                                latency=_latency,
                            )
                        )
                    except (ImportError, AttributeError):
                        pass
                # ── 方法论追踪: 自动记录文件操作 + 触发升级 ──
                try:
                    from core.methodology import get_methodology_state

                    m_state = get_methodology_state()
                    m_state.record_tool(fname)
                    # 追踪写入文件
                    if fname in self._WRITE_TOOLS:
                        path = _json.loads(fargs).get("path") or _json.loads(fargs).get("file_path", "")
                        if path:
                            m_state.files_touched.append(path)
                            # 文件数超阈值 → 自动升级
                            n = len(set(m_state.files_touched))
                            if n > 3 and m_state.task_level.value in ("micro", "normal"):
                                m_state.escalate(f"files>{n}")
                            elif n > 1 and m_state.task_level.value == "micro":
                                m_state.escalate("files>1")
                except (ImportError, _json.JSONDecodeError, OSError):
                    pass
                # Fold oversized tool results for cleaner display
                # ⚠️  _display is for UI only — tool_result stays intact for model & error detection
                _display = tool_result
                if isinstance(tool_result, str) and len(tool_result) > 800:
                    preview = "\n".join(tool_result.split("\n")[:5])
                    _display = f"{preview}\n... [{len(tool_result)} chars folded, result sent to model]"
                span.set_attribute("result_chars", len(tool_result) if isinstance(tool_result, str) else -1)
                metrics.increment("tool_calls")
                metrics.timing("tool_call_ms", span.duration_ms())
                # #5 Prompt Lab: 记录工具调用和错误
                try:
                    from core.prompt_lab import get_prompt_lab

                    get_prompt_lab().record_tool_call()
                    if "[错误]" in str(tool_result) or "error" in str(tool_result).lower():
                        get_prompt_lab().record_tool_error()
                except (ImportError, OSError) as e:
                    logger.debug("optional module skipped: %s", e)

                    pass
            # ── Adaptive loop limit: expand on success, shrink on cascade failures ──
            _tool_ok = not str(tool_result).startswith("[错误]") and not str(tool_result).startswith("[自愈失败]")
            if _tool_ok:
                self._consecutive_failures = 0
                self._consecutive_successes += 1
                if self._consecutive_successes > 10:
                    self._effective_max = max(self._effective_max, int(self._effective_max * 1.5))
                    self._consecutive_successes = 0
            else:
                self._consecutive_failures += 1
                self._consecutive_successes = 0
                if self._consecutive_failures >= 3:
                    self._effective_max = min(self._effective_max, _loop + 5)
                    yield ("info", f"连续 {self._consecutive_failures} 次失败 — 剩余最多 5 次重试")
            # ── 高风险工具确认：同意即执行，拒绝则占位跳过 ──
            is_confirm = any(k == "confirm" for k, _ in side_effects)
            if is_confirm:
                placeholder = f"[高风险工具 {fname}: 等待用户确认]"
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": placeholder,
                    }
                )
                yield from side_effects  # ← Confirm.ask 阻塞点
                # b. 用户同意 → 用 confirmed=True 重新执行，跳过 confirm 检查
                tool_result, exec_side_effects = self._dispatch_tool(fname, fargs, confirmed=True)
                _display = tool_result  # 同步 display 到重执行结果
                yield from exec_side_effects
                # c. 用真实结果替换占位
                self.messages[-1] = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": compress_tool_result(tool_result, self.client, self.model),
                }
                append_tool_result = False  # 已在 confirm 分支内追加
            else:
                yield from side_effects
                append_tool_result = True
            # 把 tool 执行结果 yield 给 UI，实现闭环展示
            _ui_text = _display if isinstance(_display, str) else str(_display)
            if len(_ui_text) > 2000:
                _ui_text = _ui_text[:2000] + "\n...[folded]"
            yield ("tool_result", {"name": fname, "result": _ui_text})
            if fname not in self._WRITE_TOOLS:
                executed_sigs.add(sig)
                executed_cache[sig] = tool_result  # 缓存原始完整结果
        # 上下文窗口防护：智能压缩
        if append_tool_result:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": compress_tool_result(tool_result, self.client, self.model),
                }
            )
    return False
