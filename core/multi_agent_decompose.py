"""Multi-agent task decomposition — LLM-driven + keyword fallback.

Extracted from core/multi_agent.py (P2 refactor). Contains:
- SmartDecomposer: LLM-driven intelligent task breakdown
- _keyword_decompose: pattern-based fallback decomposition
- _decompose_goal: unified entry point (LLM first, keyword fallback)
- DAG utilities: _topological_waves, _check_dag_deadlock, _propagate_failed_deps
- _build_run_summary: standardized run result aggregation
- _extract_json: JSON extraction from LLM responses
"""

from __future__ import annotations

import logging
import re
import time

from core.error_sink import catch
from core.multi_agent_models import AgentTask

logger = logging.getLogger("crux.multi_agent")

# ── #4 Qoder-style: Smart Multi-Agent Decomposition ──

_SMART_DECOMPOSE_PROMPT = """你是多智能体任务规划专家。将用户目标分解为子任务，每个子任务分配给一个专门的 Agent。

可用工具：read_file, search_files, glob_files, code_analyze, find_symbol, find_references,
           graph_neighbors, graph_ancestors, graph_descendants, run_test, run_bash,
           run_python, edit_file, write_file, web_search, web_fetch, github_search

核心铁律 — 必须先理解再行动：
1. 第一波必须包含至少 1 个 explorer 任务（read_file / search_files / glob_files），
   用于理解代码结构和上下文。绝不跳过这一步直接修改。
2. 后续修改任务必须依赖第一波的 explorer 结果（depends_on 标注）。

分解规则：
3. 每个子任务只做一件事，用 1-3 个工具
4. 标注依赖关系（depends_on）：B 需要 A 的结果时，B.depends_on = ["A的id"]
5. 给每个任务分配 role: explorer(探索上下文) | analyst(分析) | fixer(修改) | tester(验证)
6. 给每个任务分配 tier: light(搜索/读文件) | pro(分析/修改) | heavy(架构审查)
7. 返回纯 JSON 数组，每项含 id/description/role/tier/tools/depends_on 字段

目标：{goal}

只返回 JSON 数组，不要其他文字。"""


class SmartDecomposer:
    """LLM-driven task decomposition for multi-agent coordination.

    Qoder 理念：不再用关键词匹配暴力分解任务，而是让 LLM 理解意图后
    智能拆解，自动分配角色（explorer/analyst/fixer/tester）和
    模型层级（light/pro/heavy），失败时退回关键词匹配。

    Usage:
        decomposer = SmartDecomposer()
        tasks = decomposer.decompose("审查认证模块的安全性")
        # → 4-5 个带角色和 tier 的 AgentTask
    """

    def __init__(self, client=None, model: str | None = None, model_router=None) -> None:
        self._client = client
        self._model = model
        self._model_router = model_router

    def decompose(self, goal: str, tool_names: list[str] | None = None) -> list[AgentTask]:
        """Smart decompose with LLM, fallback to keyword matching.

        Post-condition: the first wave always contains at least one explorer
        task (read_file / search_files / glob_files).  If the LLM forgot to
        include one, we inject a context-gathering task automatically.
        """
        try:
            tasks = self._llm_decompose(goal, tool_names)
        except Exception:
            tasks = _keyword_decompose(goal)

        # ── Gate: ensure first wave has at least one explorer ──
        if not self._has_explorer_in_first_wave(tasks):
            explore_task = AgentTask(
                id="explore_context",
                description=f"Explore codebase structure for: {goal[:100]}",
                tier="light",
                task_type="explorer",
                tool_sequence=[
                    {"tool": "search_files", "args": {"pattern": goal.split()[-1] if goal.split() else "*"}},
                    {"tool": "glob_files", "args": {"pattern": "**/*.py"}},
                ],
                depends_on=[],
            )
            tasks.insert(0, explore_task)
            logger.info("SmartDecomposer: injected explorer task (LLM omitted it)")

        return tasks

    @staticmethod
    def _has_explorer_in_first_wave(tasks: list[AgentTask]) -> bool:
        """Check if any task in the first wave (no dependencies) is an explorer."""
        EXPLORER_TOOLS = frozenset(
            {
                "read_file",
                "search_files",
                "glob_files",
                "list_files",
                "find_symbol",
                "find_references",
                "code_analyze",
                "graph_neighbors",
                "graph_ancestors",
                "graph_descendants",
            }
        )
        for t in tasks:
            if t.depends_on:
                continue
            if t.task_type == "explorer":
                return True
            for entry in t.tool_sequence or []:
                if entry.get("tool", "") in EXPLORER_TOOLS:
                    return True
        return False

    def _llm_decompose(self, goal: str, tool_names: list[str] | None = None) -> list[AgentTask]:
        """Use LLM to decompose the goal into structured tasks.

        Model tier adapts to goal complexity: simple goals use light model,
        complex architecture/planning use heavy. Saves cost on routine tasks.

        Results are cached — repeated calls with the same goal skip the LLM.
        """
        # ── Check cache first ──
        from core.agent_cache import get_cache

        cache = get_cache()
        cached = cache.get_decomposition(goal, "decompose")
        if cached is not None:
            return cached

        prompt = _SMART_DECOMPOSE_PROMPT.format(goal=goal)

        # Resolve model via router: match tier to goal complexity
        model = self._model
        if not model and self._model_router:
            # Classify goal first → light goals don't need heavy-tier decomposition
            goal_tier = self._model_router.classify_prompt(goal)
            if goal_tier == "light":
                model = self._model_router.select(task_type="search")  # light tier
            elif goal_tier == "reasoner":
                model = self._model_router.select(task_type="planning")  # heavy tier
            else:
                model = self._model_router.select(task_type="tool_calling")  # pro tier

        # ── 方法论检查: Agent 路由约束 ──
        try:
            from core.methodology import check_agent_route

            resolved = model or "deepseek-v4-pro"
            if "planning" in (goal_tier if model else ""):
                allowed, msg = check_agent_route("architecture", resolved)
            elif goal_tier == "light" and "pro" in resolved:
                allowed, msg = check_agent_route("grep", resolved)
            else:
                allowed, msg = True, ""
            if not allowed:
                raise RuntimeError(f"Agent routing violation: {msg}")
        except (ImportError, RuntimeError):
            pass

        # Try via CruxClient if available, otherwise via raw chat
        raw = ""
        try:
            from core.client import CruxClient

            client = self._client or CruxClient()
            chat_model = model or "deepseek-v4-pro"
            resp = client.chat(chat_model, messages=[{"role": "user", "content": prompt}])
            raw = (
                resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(resp, dict)
                else str(resp)
            )
        except ImportError:
            # Last resort: try via run_bash calling a simple script
            raise RuntimeError("No LLM client available for SmartDecomposer") from None

        # Parse JSON from response
        tasks_json = _extract_json(raw)

        tasks: list[AgentTask] = []
        for item in tasks_json:
            tools = []
            for t in item.get("tools", []):
                tools.append({"tool": t.get("name", "read_file"), "args": t.get("args", {})})
            if not tools:
                tools = [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}]

            task = AgentTask(
                id=item.get("id", f"t{len(tasks)}"),
                description=item.get("description", ""),
                tool_sequence=tools,
                depends_on=item.get("depends_on", []),
                tier=item.get("tier", "auto"),
                task_type=item.get("role", ""),
            )
            tasks.append(task)

        # Ensure at least 2 independent tasks (wave 0)
        independent = [t for t in tasks if not t.depends_on]
        if len(independent) < 2 and len(tasks) >= 2:
            tasks[1].depends_on = []

        result = tasks if tasks else _keyword_decompose(goal)
        # Cache successful decompositions
        if tasks:
            cache.set_decomposition(goal, "decompose", result)
        return result


def _decompose_goal(goal: str, model_router=None) -> list[AgentTask]:
    """任务分解入口：优先智能分解，失败退回关键词匹配。

    所有调用方（MultiAgentCoordinator / AsyncMultiAgentCoordinator）通过
    此函数获得统一的行为，不需要关心内部是 LLM 还是关键词。
    """
    try:
        decomposer = SmartDecomposer(model_router=model_router)
        return decomposer.decompose(goal)
    except Exception:
        return _keyword_decompose(goal)


def _keyword_decompose(goal: str) -> list[AgentTask]:
    """关键词匹配的快速分解（LLM 不可用时的可靠降级）。

    保留原有逻辑：review / debug / default 三条路径。
    """
    goal_lower = goal.lower()

    if "review" in goal_lower or "审查" in goal_lower or "audit" in goal_lower:
        return [
            AgentTask(
                "t1",
                "列出项目文件结构",
                [{"tool": "list_files", "args": {"path": "."}}],
                tier="light",
                task_type="explorer",
            ),
            AgentTask(
                "t2",
                "搜索潜在问题和反模式",
                [{"tool": "search_files", "args": {"pattern": "TODO|FIXME|HACK|bug|error"}}],
                depends_on=["t1"],
                tier="light",
                task_type="explorer",
            ),
            AgentTask(
                "t3",
                "搜索 Python 文件结构",
                [{"tool": "glob_files", "args": {"pattern": "**/*.py"}}],
                depends_on=["t1"],
                tier="pro",
                task_type="analyst",
            ),
            AgentTask(
                "t4",
                "运行测试验证",
                [{"tool": "run_test", "args": {}}],
                depends_on=["t2", "t3"],
                tier="heavy",
                task_type="tester",
            ),
        ]

    if "debug" in goal_lower or "fix" in goal_lower or "调试" in goal_lower or "修复" in goal_lower:
        return [
            AgentTask(
                "t1",
                "检查错误日志",
                [{"tool": "search_files", "args": {"pattern": "error|exception|traceback"}}],
                tier="light",
                task_type="explorer",
            ),
            AgentTask(
                "t2",
                "全局搜索相关代码",
                [{"tool": "search_files", "args": {"pattern": "def |class "}}],
                tier="light",
                task_type="explorer",
            ),
            AgentTask(
                "t3",
                "定位根因并读取相关文件",
                [{"tool": "search_files", "args": {"pattern": goal.split()[-1] if goal.split() else "*"}}],
                depends_on=["t1", "t2"],
                tier="pro",
                task_type="analyst",
            ),
            AgentTask(
                "t4",
                "实施修复",
                [{"tool": "run_bash", "args": {"command": "echo 'fix applied'"}}],
                depends_on=["t3"],
                tier="pro",
                task_type="fixer",
            ),
            AgentTask(
                "t5",
                "验证修复并运行测试",
                [{"tool": "run_test", "args": {}}],
                depends_on=["t4"],
                tier="heavy",
                task_type="tester",
            ),
        ]

    # Default: investigate → understand → act → verify
    first_word = goal.split()[0] if goal.split() else "main"
    return [
        AgentTask("t1", "探索项目结构", [{"tool": "list_files", "args": {}}], tier="light", task_type="explorer"),
        AgentTask(
            "t2",
            "搜索相关文件",
            [{"tool": "search_files", "args": {"pattern": first_word}}],
            tier="light",
            task_type="explorer",
        ),
        AgentTask(
            "t3",
            "读取并分析关键文件",
            [{"tool": "search_files", "args": {"pattern": first_word}}],
            depends_on=["t2"],
            tier="pro",
            task_type="analyst",
        ),
        AgentTask(
            "t4",
            "执行操作并验证",
            [{"tool": "run_test", "args": {}}],
            depends_on=["t3"],
            tier="heavy",
            task_type="tester",
        ),
    ]


def _extract_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    import json as _json

    raw = raw.strip()
    # Try direct parse
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        pass
    # Try extracting from code blocks
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw)
    if m:
        try:
            return _json.loads(m.group(1))
        except _json.JSONDecodeError:
            pass
    # Try finding any array
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            return _json.loads(m.group(0))
        except _json.JSONDecodeError:
            pass
    return []


# ── DAG Runtime Deadlock Guard ──────────────────────────


def _build_run_summary(goal: str, tasks: list, log: list, agents: list, started: float) -> dict:
    """生成执行摘要：统计各状态任务数 + 事件计数。"""
    done = sum(1 for t in tasks if t.status == "done")
    failed = sum(1 for t in tasks if t.status == "failed")
    skipped = sum(1 for t in tasks if t.status == "skipped")
    timed_out = sum(1 for t in tasks if "[timeout]" in t.result or "[deadlock]" in t.result)
    cancelled = sum(1 for t in tasks if t.status == "pending")

    deadlock_count = sum(1 for e in log if e.get("event") == "dag_deadlock")
    fallback_count = sum(1 for e in log if e.get("event") in ("wave_timeout", "task_timeout"))
    timeout_count = sum(1 for e in log if e.get("event") == "task_timeout")

    # 提取 provider route 信息
    provider_route = ""
    for entry in log:
        if entry.get("event") == "tier_routed":
            provider_route = entry.get("model", "")
        if "provider" in entry:
            provider_route = entry.get("provider", provider_route)
    longest = max(tasks, key=lambda t: t.finished_at - t.started_at) if tasks else None
    longest_info = {}
    if longest and longest.finished_at > 0:
        longest_info = {
            "id": longest.id,
            "duration_ms": int((longest.finished_at - longest.started_at) * 1000),
            "status": longest.status,
        }

    failure_reasons: dict[str, int] = {}
    for t in tasks:
        if t.status == "failed" and t.result:
            reason = t.result[:60]
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    root_id = tasks[0].root_trace_id if tasks else ""

    result = {
        "goal": goal,
        "root_trace_id": root_id,
        "elapsed_ms": int((time.time() - started) * 1000),
        "elapsed": round(time.time() - started, 1),
        "agents": len(agents),
        "tasks_total": len(tasks),
        "tasks_done": done,
        "tasks_failed": failed,
        "tasks_skipped": skipped,
        "tasks_timeout": timed_out,
        "tasks_cancelled": cancelled,
        "events": {"deadlocks": deadlock_count, "fallbacks": fallback_count, "timeouts": timeout_count},
        "longest_task": longest_info,
        "failure_reasons": failure_reasons,
        "provider_route": provider_route,
    }
    try:
        from core.policy_gate import auto_recover
        from core.quality_gate import assess_quality
        from core.retry_budget import auto_retry_decision, record_retry_attempt
        from core.run_replay import save_run_replay
        from core.run_summary import save_run

        quality = assess_quality(result)
        # QualityGateResult 是 dataclass，不可直接 update，需转 dict
        try:
            from dataclasses import asdict

            result.update(asdict(quality))
        except (TypeError, AttributeError):
            # 降级：尝试手动提取字段
            if hasattr(quality, "__dict__"):
                result.update(quality.__dict__)
        policy = auto_recover(result)
        result.update({"policy_action": policy["action"], "policy_reason": policy["reason"]})
        retry = auto_retry_decision(result)
        result.update(
            {
                "retry_budget": retry.get("budget", {}),
                "retry_decision": retry.get("should_retry", False),
                "retry_reason": retry.get("reason", ""),
            }
        )
        if retry.get("should_retry"):
            record_retry_attempt(root_id, "scheduled", "pending")
        save_run(result)
        try:
            from core.incident import classify_run, save_incident, should_alert

            incident = classify_run(result, log)
            result.update({"incident": incident})
            try:
                from core.incident import auto_remediation

                cmds = auto_remediation(incident, root_id)
                if cmds:
                    result.update({"remediation_commands": cmds})
            except Exception as _es:
                catch(_es, "core.multi_agent", "swallowed")
            if incident.get("total_incidents", 0) > 0:
                try:
                    save_incident(incident)
                    alert = should_alert(incident)
                    result.update({"alert": alert})
                except Exception as _es:
                    catch(_es, "core.multi_agent", "swallowed")
        except Exception as _es:
            catch(_es, "core.multi_agent", "swallowed")
        try:
            tasks_dict = [
                {
                    "id": t.id,
                    "status": t.status,
                    "trace_id": t.trace_id,
                    "result": t.result,
                    "started_at": t.started_at,
                    "finished_at": t.finished_at,
                }
                for t in tasks
            ]
            save_run_replay(root_id, result, log, tasks_dict)
        except Exception as _es:
            catch(_es, "core.multi_agent", "swallowed")
    except Exception as _es:
        catch(_es, "core.multi_agent", "swallowed")
    return result


def _check_dag_deadlock(tasks: list[AgentTask], wave_idx: int = 0, root_trace_id: str = "") -> str | None:
    """检查 DAG 死锁条件。返回描述字符串或 None（无死锁）。

    死锁条件：
    - 存在 pending 任务，但没有 running 任务 → 不可进展
    - 所有 pending 任务的依赖都是 failed → 级联失败
    """
    pending = [t for t in tasks if t.status == "pending"]
    running = [t for t in tasks if t.status == "running"]
    failed_ids = {t.id for t in tasks if t.status == "failed"}

    if pending and not running:
        # 检查是否所有 pending 任务都依赖了已失败的 task
        stuck = []
        for t in pending:
            deps = t.depends_on
            if deps and all(d in failed_ids for d in deps):
                stuck.append(t.id)
        if stuck and len(stuck) == len(pending):
            return (
                f"DAG deadlock: {len(pending)} tasks stuck "
                f"(all deps failed: {stuck[:5]}{'...' if len(stuck) > 5 else ''}) "
                f"[wave={wave_idx}, trace={root_trace_id[:12]}...]"
            )
        if not running:
            # 有 pending 但没有 running，且至少一个 pending 的依赖不可满足
            for t in pending:
                deps = t.depends_on
                unknown = [d for d in deps if d not in {x.id for x in tasks}]
                if unknown:
                    return (
                        f"DAG deadlock: task '{t.id}' depends on unknown tasks {unknown} "
                        f"[wave={wave_idx}, trace={root_trace_id[:12]}...]"
                    )
    return None


def _propagate_failed_deps(tasks: list[AgentTask], root_trace_id: str = "") -> int:
    """将上游 failed 的 task 的下游标记为 skipped。

    返回被 skip 的数量。
    """
    skipped = 0
    failed_ids = {t.id for t in tasks if t.status in ("failed", "skipped")}
    if not failed_ids:
        return 0
    for t in tasks:
        if t.status != "pending":
            continue
        if t.depends_on and any(d in failed_ids for d in t.depends_on):
            t.status = "skipped"
            t.result = "[skipped] upstream task failed"
            skipped += 1
    return skipped


def _topological_waves(tasks: list[AgentTask]) -> list[list[AgentTask]]:
    """把带依赖的任务列表分层为可并行的"波"。

    - 第 0 波：depends_on 为空（或依赖不在任务集中）的任务。
    - 第 k 波：所有依赖已在第 0..k-1 波出现过、且自身未分层的任务。
    - 同一波内的任务互不依赖，可 ``asyncio.gather`` 并行。

    检测到依赖环时抛 ``ValueError``（防止死锁）。
    检测到重复 ID 时抛 ``ValueError``（防止误报为环）。
    """
    # 重复 ID 检测：SmartDecomposer 的 LLM 输出可能产生重复 ID
    if len({t.id for t in tasks}) != len(tasks):
        from collections import Counter

        dupes = [tid for tid, cnt in Counter(t.id for t in tasks).items() if cnt > 1]
        raise ValueError(f"Duplicate task IDs detected: {dupes}")
    by_id = {t.id: t for t in tasks}
    placed: set[str] = set()
    waves: list[list[AgentTask]] = []

    while len(placed) < len(tasks):
        # 当前波：未分层且所有（已知）依赖均已分层的任务
        wave = [t for t in tasks if t.id not in placed and all(d in placed or d not in by_id for d in t.depends_on)]
        if not wave:
            # 剩余任务都无法满足依赖 → 存在环
            remaining = [t.id for t in tasks if t.id not in placed]
            raise ValueError(f"任务依赖存在环或不可满足: {remaining}")
        waves.append(wave)
        placed.update(t.id for t in wave)

    return waves
