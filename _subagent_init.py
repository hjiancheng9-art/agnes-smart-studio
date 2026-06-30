class SubAgent:
    """An independent sub-agent with its own session history and tool-calling loop.

    Unlike the old spawn_subagent(), this agent can:
    - Execute tools in a loop (up to max_rounds)
    - Maintain independent conversation history
    - Report results back to the parent
    """

    def __init__(
        self,
        client,
        tools=None,
        model: str = "deepseek-v4-pro",
        max_rounds: int = 5,
        tier: str = "auto",
        task_type: str = "",
    ) -> None:
        """Init sub-agent.

        Args:
            model: 显式模型 ID（向后兼容，优先级最高）
            tier: "auto" / "light" / "pro" / "heavy" — auto 时按 task_type 路由
            task_type: 传给 ModelRouter.select() 的任务类型（tier=auto 时生效）
        """
        self.client = client
        self.tools = tools
        self.max_rounds = max_rounds
        self.history: list[dict] = []
        self.context_mgr = ContextManager(max_tokens=20000)
        self._session_approved: set[str] = set()  # high-risk tools auto-approved for this session
        # tier 路由：model 显式指定时尊重之；否则按 tier/task_type 自动选
        if model != "deepseek-v4-pro" or tier == "auto":
            # 用户显式传了 model（非默认值）→ 直接用
            if model != "deepseek-v4-pro":
                self.model = model
            else:
                router = ModelRouter()
                if tier in ("light", "pro", "heavy"):
                    self.model = router.select_for_tier(tier)
                elif task_type:
                    self.model = router.select(task_type=task_type)
                else:
                    self.model = model  # auto + 无 task_type → 退回默认
        else:
            self.model = model

    def run(self, task: str, system_prompt: str = "") -> str:
        """Execute a task with tool-calling loop.

        Returns the final text result.
        """
        if not system_prompt:
            system_prompt = SUBAGENT_PROMPT.format(task=task)

        self.history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        tool_defs = None
        if self.tools and self.tools.definitions:
            tool_defs = self.tools.definitions

        for _round_num in range(self.max_rounds):
            # Auto-compress if needed
            self.history = self.context_mgr.auto_compress_if_needed(self.history, self.client)

            try:
                r = self.client.chat(
                    model=self.model,
                    messages=self.history,
                    max_tokens=4096,
                    tools=tool_defs,
                )
            except (OSError, ValueError, RuntimeError) as e:
                return f"[SubAgent error] {e}"

            msg = r["choices"][0]["message"]
            self.history.append(msg)

            # Check if model wants to call tools
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                # No tool calls - return the text response
                return msg.get("content", "")

            # Execute each tool call
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args_str = fn.get("arguments", "{}")

                try:
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except json.JSONDecodeError:
                    tool_args = {}

                # Execute tool
                if self.tools and self.tools.has(tool_name):
                    # 高风险守卫：SubAgent 无法弹确认框，命中即拒绝
                    # 与 chat.py._dispatch_tool 的 _HIGH_RISK_TOOLS 对齐
                    _HIGH_RISK = {
                        "git_add_commit",
                        "git_push",
                        "git_pr_create",
                        "git_pr_merge",
                    }
                    is_risky = tool_name in _HIGH_RISK or (
                        tool_name == "github_write_file" and not tool_args.get("branch", "").strip()
                    )
                    if is_risky:
                        result = (
                            f"[安全拦截] 工具 '{tool_name}' 属高风险写操作，"
                            "SubAgent 自主循环不允许执行，请由主会话确认后调用。"
                        )
                    else:
                        result = self.tools.execute(tool_name, tool_args)
                else:
                    result = f"[Error] Unknown tool: {tool_name}"

                # Add tool result to history
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result[:4000],  # Truncate long results
                    }
                )

        return "[SubAgent] Max rounds reached without final answer."


# ======================================================================
# Multi-Model Intelligent Router
# ======================================================================


# ── Heuristic prompt classification (for main chat auto-model) ──

_CODE_SIGNALS = re.compile(
    r"```|import\s+\w+|def\s+\w+|class\s+\w+|"
    r"Traceback|Error:|Exception|"
    r"\.py\b|\.js\b|\.ts\b|\.go\b|\.rs\b|"
    r"function|component|hook|api|endpoint|"
    r"bug|fix|debug|refactor|test|commit|"
    r"error|crash|fail|broken|"
    r"函数|类\b|模块|接口|错误|异常|修复|提交|测试|重构|"
    r"代码|实现|写|改|加|补|删|优化|拆分",
    re.IGNORECASE,
)

_STRONG_REASONER = re.compile(
    r"security\s+(?:audit|review|assessment|hole|flaw|vulnerability)|"
    r"threat\s+model|attack\s+(?:surface|vector|tree)|"
    r"architecture\s+(?:design|review|decision)|"
    r"architect\s+(?:a\s+)?(?:new|system|solution|pattern)|"
    r"refactor\s+(?:across|entire|whole)|"
    r"event\s+sourcing|CQRS|domain[\s-]?driven|"
    r"comprehensive\s+(?:review|audit|analysis)|"
    r"root\s+cause|diagnose\s+(?:this|the|why)|"
    r"database\s+(?:schema|migration|design|architecture)|"
    r"investigate\s+(?:this|the|why|how)|"
    r"optimize\s+(?:.*\s)?performance|"
    r"架构\s*(?:设计|审查|决策|重构)|"
    r"安全\s*(?:审计|漏洞|审查|扫描)|"
    r"(?:全面|深度|彻底|详细)\s*(?:审查|分析|检查|方案)|"
    r"性能\s*(?:优化|调优|瓶颈)|"
    r"数据库\s*(?:设计|迁移|架构)|"
    r"根因|底层原因|排查|"
    r"内存\s*泄漏|OOM|死循环|"
    r"分析\s*(?:这段|这个|代码|为什么|原因)",
    re.IGNORECASE,
)

_MODERATE_REASONER = re.compile(
    r"architect(?:ure|ural)?\b|"
    r"design\s+(?:system|pattern|decision|doc|spec)|"
    r"multi[\s-]?file|"
    r"refactor|"
    r"security\s+vulnerability|"
    r"why\s+(?:.*\s)?(?:fail|crash|break|wrong)|"
    r"\bmath\b|algorithm\s+(?:design|analysis|complexity|ic)|"
    r"proof|prove\s+(?:that|it|the|this)|"
    r"distributed|concurrent|race\s+condition|deadlock|"
    r"scal(?:e|able|ability)\b|throughput|latency|"
    r"migrat(?:e|ion)\s+(?:plan|strategy|to|from)|"
    r"upgrade\s+.*major|breaking\s+change|"
    r"deep\s+(?:dive|analysis)\b|"
    r"设计\s*(?:方案|模式|系统)|"
    r"算法|排序|搜索|加密|解密|"
    r"为什么\s*(?:失败|崩溃|出错|不对)|"
    r"多\s*(?:文件|模块|服务)|"
    r"重构\s*(?:整个|全面|大|代码)|"
    r"迁移\s*(?:计划|方案|到)|"
    r"并发|死锁|扩展|吞吐|延迟",
    re.IGNORECASE,
)

_LIGHT_SIGNALS = re.compile(
    r"^(?:what\s+is|who\s+is|when\s+|where\s+|"
    r"how\s+(?:do|to|can)\s+I\s+|"
    r"show\s+me|list\s+|find\s+|search\s+|grep\s+|"
    r"explain\s+(?:this|what)|what\s+does|meaning\s+of|"
    r"definition\s+of|example\s+of|"
    r"\bformat\b|\bconvert\b|\btranslate\b|"
    r"run\s+(?:the\s+)?(?:test|pytest|smoke|check|lint))",
    re.IGNORECASE,
)

_LIGHT_COMMANDS = re.compile(
    r"^(?:run|执行|跑)\s*(?:测试|test|smoke|check|lint)|"
    r"^(?:format|lint|sort|organize)\s",
    re.IGNORECASE,
)


def _count_matches(pattern: re.Pattern, text: str) -> int:
    """Count non-overlapping matches of pattern in text."""
    return sum(1 for _ in pattern.finditer(text))


def _resolve_tier_from_dict(tier: str, provider_models: dict[str, str]) -> str:
    """Map a tier to an actual model ID from a provider's model dict.

    Search order tries exact tier first, then falls back through canonical tiers.
    Normalizes 'reasoner' to look for 'reasoner' key, then 'heavy', then 'pro', etc.
    """
    # Build search order: exact tier, then canonical fallback chain
    search_order = [tier]
    if tier == "reasoner":
        search_order += ["heavy", "pro", "light"]
    elif tier == "heavy":
        search_order += ["pro", "light"]
    elif tier == "pro":
        search_order += ["light", "heavy", "reasoner"]
    elif tier == "light":
        search_order += ["pro", "heavy"]
    else:
        search_order += ["pro", "light", "heavy", "reasoner"]

    for t in search_order:
        if t in provider_models:
            return provider_models[t]
    if provider_models:
        return next(iter(provider_models.values()))
    return "unknown"

