"""Policy regression tests — validate that provider routing doesn't regress."""

import json
import os
import time

from core.config import OUTPUT_DIR

REGRESSION_FILE = os.path.join(OUTPUT_DIR, "policy_regression.jsonl")


def record_route_decision(request: dict, selected: list[str], circuit_states: dict[str, str]) -> None:
    """记录一次路由决策，用于回归分析。"""
    entry = {
        "timestamp": time.time(),
        "request": request,
        "selected": selected,
        "circuit_states": circuit_states,
    }
    os.makedirs(os.path.dirname(REGRESSION_FILE), exist_ok=True)
    with open(REGRESSION_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_regression(request: dict, expected_first: str) -> tuple[bool, str]:
    """检查路由决策是否与预期一致。"""
    from core.provider import get_provider_manager
    from core.provider_policy import select_candidates

    try:
        mgr = get_provider_manager()
        all_pids = list(mgr.providers.keys())
        circuit_states = {p: mgr.state.circuit_state(p) for p in all_pids}
        selected = select_candidates(request, all_pids, circuit_states)
        actual_first = selected[0] if selected else "none"
        passed = actual_first == expected_first
        msg = f"expected={expected_first}, actual={actual_first}"
        if not passed:
            msg += f" ROUTE_CHANGED! full={selected}"
        record_route_decision(request, selected, circuit_states)
        return passed, msg
    except Exception as e:
        return False, f"error: {e}"


def run_regression_suite() -> list[dict]:
    """运行回归测试套件。"""
    tests = [
        (
            "coding task",
            {"task_type": "code", "require_code": True, "budget_remaining": 100, "prefer_local": False},
            "deepseek",
        ),
        (
            "general text",
            {"task_type": "text", "require_code": False, "budget_remaining": 100, "prefer_local": False},
            "deepseek",
        ),
        (
            "low budget",
            {"task_type": "text", "require_code": False, "budget_remaining": 10, "prefer_local": True},
            "local",
        ),
    ]

    results = []
    for name, req, expected in tests:
        passed, msg = check_regression(req, expected)
        results.append({"test": name, "passed": passed, "message": msg})
    return results
