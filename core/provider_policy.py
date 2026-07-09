"""ProviderPolicy — 策略路由，替代固定 fallback 链。"""


def score_provider(pid: str, request: dict, circuit_states: dict[str, str]) -> float:
    """对 provider 打分，越高越优先。

    考虑因素：task_type、budget、circuit_state、latency、prefer_local
    """
    score = 50.0  # 基础分
    task_type = request.get("task_type", "text")
    require_code = request.get("require_code", False)
    prefer_local = request.get("prefer_local", False)
    budget = request.get("budget_remaining", 100)

    # circuit breaker：OPEN 直接淘汰
    circuit = circuit_states.get(pid, "CLOSED")
    if circuit == "OPEN":
        return -100
    if circuit == "HALF_OPEN":
        score -= 30

    # 按 provider 特性打分
    if pid == "deepseek":
        if require_code or task_type in ("code", "debug", "refactor"):
            score += 30  # 强代码
        score += 15  # 综合实力
    elif pid == "crux":
        if task_type in ("image", "video"):
            score += 40  # 媒体生成优势
        score += 10
    elif pid == "zhipu":
        if prefer_local:
            score += 20
        score += 5
    elif pid == "local":
        if prefer_local:
            score += 30
        if budget < 20:
            score += 25  # 低成本优势
        score -= 10  # 能力有限
    else:
        score -= 20  # 未知 provider

    # budget 敏感
    if budget < 30 and pid in ("deepseek", "crux"):
        score -= 15  # 高成本 provider 在预算不足时降权

    # 历史表现调整
    try:
        from core.provider_history import adapt_score

        score = adapt_score(pid, score)
    except ImportError:
        pass

    return score


def select_candidates(request: dict, available: list[str], circuit_states: dict[str, str]) -> list[str]:
    """返回排序后的 provider 候选列表（最优在前）。"""
    scored = [(pid, score_provider(pid, request, circuit_states)) for pid in available]
    scored.sort(key=lambda x: -x[1])  # 按分数降序
    return [pid for pid, s in scored if s > -1]


def explain_routing(pid: str, request: dict, circuit_states: dict[str, str]) -> list[str]:
    """解释某个 provider 的评分明细。"""
    reasons = []
    score = 50.0
    reasons.append("base=50")

    task_type = request.get("task_type", "text")
    require_code = request.get("require_code", False)
    prefer_local = request.get("prefer_local", False)
    budget = request.get("budget_remaining", 100)

    circuit = circuit_states.get(pid, "CLOSED")
    if circuit == "OPEN":
        return [f"{pid}: excluded (circuit=OPEN)"]
    if circuit == "HALF_OPEN":
        score -= 30
        reasons.append("circuit=HALF_OPEN: -30")

    if pid == "deepseek":
        if require_code or task_type in ("code", "debug", "refactor"):
            score += 30
            reasons.append("strong_coding: +30")
        score += 15
        reasons.append("general_power: +15")
    elif pid == "crux":
        if task_type in ("image", "video"):
            score += 40
            reasons.append("media_expert: +40")
        score += 10
        reasons.append("general: +10")
    elif pid == "zhipu":
        if prefer_local:
            score += 20
            reasons.append("local_preferred: +20")
        score += 5
        reasons.append("general: +5")
    elif pid == "local":
        if prefer_local:
            score += 30
            reasons.append("local_preferred: +30")
        if budget < 20:
            score += 25
            reasons.append("low_cost: +25")
        score -= 10
        reasons.append("limited_capability: -10")

    if budget < 30 and pid in ("deepseek", "crux"):
        score -= 15
        reasons.append("budget_constraint: -15")

    try:
        from core.provider_history import adapt_score

        adjusted = adapt_score(pid, score)
        diff = round(adjusted - score, 1)
        if diff != 0:
            reasons.append(f"history_adjust: {diff:+g}")
            score = adjusted
    except ImportError:
        pass

    reasons.append(f"total={score:.1f}")
    return reasons


def format_explain(pid: str, request: dict, circuit_states: dict[str, str]) -> str:
    """格式化为可读的评分解释。"""
    reasons = explain_routing(pid, request, circuit_states)
    return f"{pid}: {' | '.join(reasons)}"


def format_route(selected: list[str]) -> str:
    """格式化路由结果为可读字符串。"""
    if not selected:
        return "无可用 provider"
    return " → ".join(selected)
