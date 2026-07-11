"""成本 / Token / 预算追踪 — 捕获每次 API 调用的 usage 并按模型单价算费

补上 crux-smart-studio 最致命的商业化缺口：多 provider 工作室（模型 cost
1~10 差 10 倍）此前零花费追踪，observability.py 只记耗时。

设计：
- PRICING 表：每模型 {input_per_1k, output_per_1k} 美元单价 + 图/视频按次计费
- record_usage(model, kind, usage_dict): 每次调用后写入 cost_log.jsonl + 累加
- summary(): 汇总（总花费/按模型/按天/按类型）
- BudgetGuard: 预算上限，超限返回警告字符串供调用方决策

与 observability 解耦：observability 记技术指标（耗时/状态），
本模块记财务指标（token/花费），两者互补，各写各的文件。
"""

import contextlib
import json
import threading
from datetime import datetime

from core.config import OUTPUT_DIR

__all__ = [
    "COST_LOG",
    "COST_STATE",
    "calc_cost",
    "check_budget",
    "get_daily_breakdown",
    "get_recent_records",
    "get_summary",
    "record_usage",
    "reset_cost",
    "set_budget",
]

COST_LOG = OUTPUT_DIR / "cost_log.jsonl"
COST_STATE = OUTPUT_DIR / "cost_state.json"  # 累加缓存 + 预算设置

# ════════════════════════════════════════════════════════════
#  定价表（美元；按需更新；未知模型走默认估值）
# ════════════════════════════════════════════════════════════
# 单位：text 模型 input/output_per_1k = 每千 token 美元
#       image/video 模型 per_call = 每次调用固定美元
# 注意：条目既含 "kind"（str）又含费率（float），故值为 dict[str, str | float]
PRICING: dict[str, dict[str, str | float]] = {
    # ── 文本/对话模型（每千 token 美元）──
    "agnes-2.0-flash": {"kind": "text", "input_per_1k": 0.003, "output_per_1k": 0.012},
    "agnes-2.1-flash": {"kind": "text", "input_per_1k": 0.003, "output_per_1k": 0.012},
    "deepseek-v4-pro": {"kind": "text", "input_per_1k": 0.002, "output_per_1k": 0.008},
    "deepseek-v4-flash": {"kind": "text", "input_per_1k": 0.001, "output_per_1k": 0.004},
    # ── 图像模型（每次调用固定）──
    "agnes-image-2.0-flash": {"kind": "image", "per_call": 0.02},
    "agnes-image-2.1-flash": {"kind": "image", "per_call": 0.03},
    # ── 视频模型（每次调用固定，较贵）──
    "agnes-video-v2.0": {"kind": "video", "per_call": 0.35},
}

# 未知模型的兜底估值（偏保守，避免低估花费）
_DEFAULT_PRICING = {
    "text": {"input_per_1k": 0.003, "output_per_1k": 0.012},
    "image": {"per_call": 0.02},
    "video": {"per_call": 0.30},
}


def _get_pricing(model: str, kind: str) -> dict[str, str | float]:
    """获取模型定价 — 优先从 MODEL_REGISTRY（single source of truth），其次 PRICING 兜底。"""
    # 1. 优先查 MODEL_REGISTRY.pricing
    try:
        from core.provider import MODEL_REGISTRY

        info = MODEL_REGISTRY.get(model)
        if info and info.pricing:
            return {"kind": info.model_type, **info.pricing}
    except ImportError:
        pass
    # 2. 回退到本地 PRICING 表（向后兼容）
    p = PRICING.get(model)
    if p:
        return p
    # 3. 按名字启发式推断 kind
    if "image" in model.lower():
        return {"kind": "image", **_DEFAULT_PRICING["image"]}
    if "video" in model.lower():
        return {"kind": "video", **_DEFAULT_PRICING["video"]}
    return {"kind": kind, **_DEFAULT_PRICING.get(kind, _DEFAULT_PRICING["text"])}


def calc_cost(model: str, kind: str, usage: dict | None = None, call_count: int = 1) -> float:
    """计算单次/多次调用花费（美元）。

    text 模型：按 usage.prompt_tokens / completion_tokens 算
    image/video 模型：按调用次数算（usage 通常无 token）
    """
    pricing = _get_pricing(model, kind)
    pkind = pricing.get("kind", kind)

    if pkind == "text":
        # 文本模型：必须有 usage dict 才能按 token 计费
        # usage 缺失时返回 0.0（不回退到 per_call，避免误收固定费）
        if usage:
            pt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            ct = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("output_tok") or 0
            in_rate = float(pricing["input_per_1k"])
            out_rate = float(pricing["output_per_1k"])
            return pt / 1000.0 * in_rate + ct / 1000.0 * out_rate
        return 0.0

    # 图像/视频按次
    per_call = float(pricing.get("per_call", 0.02))
    return per_call * max(1, call_count)


# ════════════════════════════════════════════════════════════
#  记录 + 累加（线程安全）
# ════════════════════════════════════════════════════════════

_lock = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat()[:19]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_state() -> dict:
    if COST_STATE.exists():
        try:
            return json.loads(COST_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"total_cost": 0.0, "total_calls": 0, "budget": None, "by_model": {}, "by_day": {}, "by_kind": {}}


def _save_state(state: dict) -> None:
    COST_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_usage(
    model: str,
    kind: str = "text",
    usage: dict | None = None,
    call_count: int = 1,
    label: str = "",
    root_trace_id: str = "",
) -> dict:
    """记录一次 API 调用的花费。

    Args:
        model: 模型 ID（如 agnes-2.0-flash）
        kind:  text / image / video
        usage: API 返回的 usage dict（text 模型含 prompt_tokens/completion_tokens）
        call_count: 图像/视频按次计费时的次数（默认1）
        label: 可选标签（如 "chat" / "generate_image" / "vision"）
        root_trace_id: 整次 multi-agent 执行的 trace ID，空时自动从 context 读取

    Returns:
        本次记录条目 dict（含 cost）
    """
    if not root_trace_id:
        try:
            from core.multi_agent import get_current_root_trace_id

            root_trace_id = get_current_root_trace_id()
        except ImportError:
            pass
    cost = calc_cost(model, kind, usage, call_count)

    # 零花费（文本模型 usage 缺失）→ 不写入日志/不累加，避免噪音
    if cost == 0.0 and kind == "text":
        return {
            "ts": _now(),
            "day": _today(),
            "model": model,
            "kind": kind,
            "label": label,
            "root_trace_id": root_trace_id,
            "usage": usage or {},
            "call_count": call_count,
            "cost": 0.0,
        }

    entry = {
        "ts": _now(),
        "day": _today(),
        "model": model,
        "kind": kind,
        "label": label,
        "usage": usage or {},
        "call_count": call_count,
        "cost": round(cost, 6),
    }

    with _lock:
        # 1) 追加到日志
        try:
            with open(COST_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

        # 2) 累加到 state 缓存
        state = _load_state()
        state["total_cost"] = round(state.get("total_cost", 0.0) + cost, 6)
        state["total_calls"] = state.get("total_calls", 0) + 1

        bm = state.setdefault("by_model", {})
        m = bm.get(model, {"cost": 0.0, "calls": 0})
        m["cost"] = round(m["cost"] + cost, 6)
        m["calls"] = m.get("calls", 0) + 1
        bm[model] = m

        bd = state.setdefault("by_day", {})
        d = bd.get(entry["day"], {"cost": 0.0, "calls": 0})
        d["cost"] = round(d["cost"] + cost, 6)
        d["calls"] = d.get("calls", 0) + 1
        bd[entry["day"]] = d

        bk = state.setdefault("by_kind", {})
        k = bk.get(kind, {"cost": 0.0, "calls": 0})
        k["cost"] = round(k["cost"] + cost, 6)
        k["calls"] = k.get("calls", 0) + 1
        bk[kind] = k

        _save_state(state)

    return entry


# ════════════════════════════════════════════════════════════
#  查询 / 汇总
# ════════════════════════════════════════════════════════════


def get_summary() -> dict:
    """获取花费汇总（从 state 缓存读，O(1)）"""
    with _lock:
        return _load_state()


def get_recent_records(limit: int = 20) -> list[dict]:
    """从 cost_log.jsonl 读最近 N 条原始记录"""
    if not COST_LOG.exists():
        return []
    try:
        with open(COST_LOG, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def get_daily_breakdown(days: int = 7) -> list[dict]:
    """最近 N 天每日花费明细"""
    with _lock:
        state = _load_state()
        by_day = state.get("by_day", {})
        sorted_days = sorted(by_day.items(), key=lambda x: x[0], reverse=True)[:days]
        return [{"day": d, "cost": v.get("cost", 0), "calls": v.get("calls", 0)} for d, v in sorted_days]


# ════════════════════════════════════════════════════════════
#  预算管理
# ════════════════════════════════════════════════════════════


def set_budget(daily_usd: float | None = None) -> dict:
    """设置每日预算上限（美元）。None = 关闭预算。

    存到 state.budget = {"daily": x}。check_budget 据此判断。
    """
    with _lock:
        state = _load_state()
        if daily_usd is None:
            state["budget"] = None
        else:
            state["budget"] = {"daily": float(daily_usd)}
        _save_state(state)
        return state.get("budget") or {}


def check_budget() -> str | None:
    """检查是否超预算。超限返回警告字符串，未超返回 None。

    基于今日累计花费 vs budget.daily。
    """
    with _lock:
        state = _load_state()
        budget = state.get("budget")
        if not budget or "daily" not in budget:
            return None
        daily_limit = budget["daily"]
        today = _today()
        today_cost = state.get("by_day", {}).get(today, {}).get("cost", 0.0)
        if today_cost >= daily_limit:
            pct = (today_cost / daily_limit * 100) if daily_limit > 0 else 999
            return (
                f"⚠️ 今日花费 ${today_cost:.4f} 已达预算上限 ${daily_limit:.4f} "
                f"({pct:.0f}%)。建议暂停高消耗操作（视频生成/大量图片）。"
            )
        if today_cost >= daily_limit * 0.8:
            pct = today_cost / daily_limit * 100
            return f"⏰ 今日花费 ${today_cost:.4f} 已用预算 {pct:.0f}% (上限 ${daily_limit:.2f})，接近上限请注意。"
        return None


def reset_cost() -> dict:
    """清零花费统计（重置 state + 归档日志）"""
    with _lock:
        old_total = _load_state().get("total_cost", 0.0)
        # 归档旧日志
        if COST_LOG.exists():
            archive = COST_LOG.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl.bak")
            with contextlib.suppress(OSError):
                COST_LOG.rename(archive)
        _save_state({"total_cost": 0.0, "total_calls": 0, "budget": None, "by_model": {}, "by_day": {}, "by_kind": {}})
        return {"cleared_total": old_total}
