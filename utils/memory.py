"""学习记忆模块 - 记录用户偏好、生成反馈、自动优化

数据文件：
  output/memory.json   - 偏好与学习数据
  output/history.json  - 生成记录（含评分）
"""

import json
import threading
from datetime import datetime
from pathlib import Path

__all__ = [
    "MEMORY_FILE",
    "SESSION_FILE",
    "build_correction_context",
    "build_evolution_context",
    "build_test_context",
    "get_all_preferences",
    "get_comparison_stats",
    "get_corrections",
    "get_evolution_stats",
    "get_preference",
    "get_recent_comparisons",
    "get_recent_sessions",
    "get_session_context",
    "get_successful_prompts",
    "get_tips",
    "get_tool_learnings",
    "get_user_context",
    "get_user_profile",
    "load_memory",
    "load_session",
    "rate_record",
    "record_comparison",
    "record_correction",
    "record_preference",
    "record_prompt_pair",
    "record_test_pattern",
    "record_tip_shown",
    "record_tool_learning",
    "save_memory",
    "save_session",
    "track_content_policy_hit",
    "track_generation",
    "update_user_profile",
]


_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
MEMORY_FILE = _OUTPUT_DIR / "memory.json"


def _ensure_file():
    if not MEMORY_FILE.exists():
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            json.dumps(
                {
                    "version": 1,
                    "created_at": datetime.now().isoformat(),
                    "preferences": {},
                    "ratings": {},
                    "stats": {
                        "total": 0,
                        "image": 0,
                        "video": 0,
                        "pipeline": 0,
                        "avg_image_rating": 0,
                        "avg_video_rating": 0,
                        "content_policy_hits": 0,
                    },
                    "patterns": [],
                    "tips_shown": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


# ── 线程安全写锁（保护 load→modify→save 的原子性）──
_memory_lock = threading.Lock()


def _safe_save_memory(data: dict):
    """原子写 memory.json（在 _memory_lock 内调用）。
    使用临时文件 + replace 模式保证写盘原子性。
    """
    tmp = MEMORY_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(MEMORY_FILE)
    except OSError:
        # 回退：直接覆盖写
        try:
            MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass


def load_memory() -> dict:
    _ensure_file()
    return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))


def save_memory(data: dict):
    with _memory_lock:
        _safe_save_memory(data)


# ── 偏好学习 ─────────────────────────────────────────


def record_preference(key: str, value):
    """记录用户偏好设置（自动去重、频率计数）"""
    with _memory_lock:
        mem = load_memory()
        prefs = mem.setdefault("preferences", {})
        if key not in prefs:
            prefs[key] = {"values": {}, "last_used": None}
        val_str = str(value)
        prefs[key]["values"][val_str] = prefs[key]["values"].get(val_str, 0) + 1
        prefs[key]["last_used"] = val_str
        _safe_save_memory(mem)


def get_preference(key: str, default=None):
    """获取最常用的偏好值"""
    mem = load_memory()
    prefs = mem.get("preferences", {}).get(key)
    if not prefs or not prefs.get("values"):
        return default
    # 返回使用次数最多的值
    best = max(prefs["values"].items(), key=lambda x: x[1])
    return best[0]


def get_all_preferences() -> dict:
    """获取所有偏好摘要"""
    mem = load_memory()
    prefs = mem.get("preferences", {})
    result = {}
    for key, data in prefs.items():
        best = max(data["values"].items(), key=lambda x: x[1]) if data["values"] else (None, 0)
        result[key] = {"favorite": best[0], "count": best[1], "total_uses": sum(data["values"].values())}
    return result


# ── 评分与反馈 ──────────────────────────────────────


def rate_record(record_id: str, rating: int):
    """给一条历史记录打分 (1-5)"""
    with _memory_lock:
        mem = load_memory()
        mem.setdefault("ratings", {})[record_id] = {
            "rating": max(1, min(5, rating)),
            "rated_at": datetime.now().isoformat(),
        }
        _update_stats(mem)
        _safe_save_memory(mem)
    # 同步更新 history.json 中的评分（在锁外，history 有自己的 IO）
    _sync_rating_to_history(record_id, rating)


def _sync_rating_to_history(record_id: str, rating: int):
    """将评分写入 history.json"""
    from utils.history import HISTORY_FILE

    if not HISTORY_FILE.exists():
        return
    records = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    for r in records:
        if r.get("id") == record_id:
            r["rating"] = rating
            r["rated_at"] = datetime.now().isoformat()
            HISTORY_FILE.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
            return


def _update_stats(mem: dict):
    """刷新统计数据"""
    ratings = mem.get("ratings", {})
    if not ratings:
        return
    vals = [r["rating"] for r in ratings.values()]
    mem["stats"]["avg_rating"] = round(sum(vals) / len(vals), 1)
    mem["stats"]["rated_count"] = len(vals)


# ── 统计追踪 ──────────────────────────────────────


def track_generation(kind: str, prompt: str, result: dict):
    """追踪一次生成，更新统计和关键词"""
    with _memory_lock:
        mem = load_memory()
        mem.setdefault("stats", {})
        mem["stats"]["total"] = mem["stats"].get("total", 0) + 1

        # 按类型统计
        kind.split("_")[0]  # text_to_image → text, image_to_video → image (unused, kept for doc)
        if "image" in kind:
            mem["stats"]["image"] = mem["stats"].get("image", 0) + 1
        if "video" in kind:
            mem["stats"]["video"] = mem["stats"].get("video", 0) + 1

        # 提取关键词模式
        keywords = _extract_keywords(prompt)
        if keywords:
            mem.setdefault("patterns", [])
            mem["patterns"].append(
                {"prompt": prompt[:120], "keywords": keywords, "kind": kind, "at": datetime.now().isoformat()[:19]}
            )
            # 只保留最近 50 条
            mem["patterns"] = mem["patterns"][-50:]

        _safe_save_memory(mem)


def track_content_policy_hit(prompt: str):
    """追踪内容过滤触发"""
    with _memory_lock:
        mem = load_memory()
        mem["stats"]["content_policy_hits"] = mem["stats"].get("content_policy_hits", 0) + 1
        _safe_save_memory(mem)


def _extract_keywords(prompt: str) -> list[str]:
    """提取用户常用的关键词"""
    # 简单按空格/逗号分割取前几个词
    try:
        # 尝试用 jieba（如果安装了），否则用简单分割
        import jieba  # type: ignore[import-not-found]

        words = [w.strip() for w in jieba.cut(prompt) if len(w.strip()) > 1]
    except ImportError:
        words = [w.strip() for w in prompt.replace("，", ",").replace("、", " ").split() if len(w.strip()) > 1]
    return words[:10]


# ── 智能提示 ──────────────────────────────────────


def get_tips() -> list[str]:
    """根据使用数据生成个性化提示"""
    mem = load_memory()
    stats = mem.get("stats", {})
    tips = []

    total = stats.get("total", 0)
    if total < 3:
        tips.append("刚开始使用？试试聊天模式(/thinking)让 AI 帮你优化提示词")
        return tips

    # 基础统计
    tips.append(f"已累计生成 {total} 次 (图片{stats.get('image', 0)}+视频{stats.get('video', 0)})")

    # 内容过滤提醒
    hits = stats.get("content_policy_hits", 0)
    if hits > 0:
        tips.append(f"提示: 有 {hits} 次提示词被拦截，尝试用中性词汇替换敏感描述")

    # 评分提醒
    rated = stats.get("rated_count", 0)
    if rated < total // 3 and total > 5:
        tips.append(f"仅 {rated}/{total} 条有评分，评分越多 AI 越懂你")

    # 偏好提示
    prefs = mem.get("preferences", {})
    if not prefs and total > 5:
        tips.append("系统正在学习你的偏好，多使用几次后会更精准")

    return tips


def record_tip_shown(tip_id: str):
    """记录已展示过的提示，避免重复"""
    with _memory_lock:
        mem = load_memory()
        mem.setdefault("tips_shown", [])
        if tip_id not in mem["tips_shown"]:
            mem["tips_shown"].append(tip_id)
            _safe_save_memory(mem)


# ════════════════════════════════════════════════
#  Prompt 进化系统 — 通过评分反馈持续优化增强效果
# ════════════════════════════════════════════════


def record_prompt_pair(user_prompt: str, enhanced_prompt: str, kind: str, rating: int, record_id: str = ""):
    """记录一组 (原始提示词, 增强后提示词, 评分) 用于进化学习

    kind: "image" 或 "video"
    高分(4-5)的记录会被作为"成功案例"用于后续优化参考
    """
    if rating < 3:  # 低分不记录，避免污染样本
        return
    with _memory_lock:
        mem = load_memory()
        mem.setdefault("prompt_evolution", {"image": [], "video": []})
        entry = {
            "user": user_prompt[:200],
            "enhanced": enhanced_prompt[:500],
            "rating": rating,
            "record_id": record_id,
            "at": datetime.now().isoformat()[:19],
        }
        mem["prompt_evolution"][kind].insert(0, entry)
        # 每种类型只保留最近 30 条高分记录
        mem["prompt_evolution"][kind] = mem["prompt_evolution"][kind][:30]
        _safe_save_memory(mem)


def get_successful_prompts(kind: str = "image", limit: int = 5) -> list[dict]:
    """获取高分提示词案例，供进化参考"""
    mem = load_memory()
    return mem.get("prompt_evolution", {}).get(kind, [])[:limit]


def build_evolution_context(kind: str = "image") -> str:
    """根据成功案例生成进化上下文，注入到 enhance_prompt 的 LLM 调用中

    让增强器学习：过去哪些增强策略产生了高分结果
    """
    successful = get_successful_prompts(kind, limit=10)
    if len(successful) < 2:  # 至少需要 2 条成功案例才有效
        return ""

    ctx = ["[历史成功案例 — 请参考以下风格生成]"]
    for i, s in enumerate(successful, 1):
        ctx.append(f"案例{i} (评分{s['rating']}/5):")
        ctx.append(f"  用户: {s['user'][:80]}")
        ctx.append(f"  增强: {s['enhanced'][:200]}")
        ctx.append("")
    ctx.append("以上案例的增强风格效果最好，请参考其结构和用词风格。")
    return "\n".join(ctx)


def get_evolution_stats() -> dict:
    """获取进化统计"""
    mem = load_memory()
    evo = mem.get("prompt_evolution", {})
    return {
        "image": len(evo.get("image", [])),
        "video": len(evo.get("video", [])),
    }


# ════════════════════════════════════════════════
#  A-B 对比测试记录 — 桥接图像对比引擎与进化系统
# ════════════════════════════════════════════════


def record_comparison(
    goal: str,
    image_paths: list[str],
    labels: list[str],
    winner: str,
    scores: dict | None = None,
    reason: str = "",
    prompts: list[str] | None = None,
) -> dict:
    """记录一次 A-B 对比测试结果，并把胜者的提示词（如有）回灌给进化系统。

    与 record_prompt_pair 不同：本函数接受"多图竞争 + 裁判判决"的结构化结果，
    自动把 winner 对应的高质量样本喂给 prompt_evolution，让进化系统积累
    真正"经过对比验证"的优质案例，而不是被动等待用户手工打分。

    Args:
        goal: 评审目标（如"哪个更符合提示词"）
        image_paths: 参与对比的图片路径列表
        labels: 与 image_paths 等长的标签（A/B/C/D 或自定义）
        winner: 胜者标签（必须在 labels 中）
        scores: {"A": {"total": 43, ...}, "B": {...}} 可选
        reason: 裁判理由，可选
        prompts: 各图对应提示词列表，可选（用于回灌进化系统）

    Returns:
        记录条目 dict（同时已写入 memory.json）
    """
    with _memory_lock:
        mem = load_memory()
        mem.setdefault("comparisons", [])

        # 安全索引：winner 标签 → 路径/prompt 索引
        winner_idx = labels.index(winner) if winner in labels else 0
        winner_idx = max(0, min(winner_idx, len(image_paths) - 1))

        entry = {
            "goal": (goal or "")[:200],
            "image_paths": [str(p) for p in image_paths][:4],
            "labels": list(labels)[:4],
            "winner": winner,
            "winner_path": str(image_paths[winner_idx]) if winner_idx < len(image_paths) else "",
            "scores": scores or {},
            "reason": (reason or "")[:300],
            "at": datetime.now().isoformat()[:19],
        }
        mem["comparisons"].insert(0, entry)
        # 最多保留 100 次对比记录
        mem["comparisons"] = mem["comparisons"][:100]
        _safe_save_memory(mem)

    # ── 回灌进化系统：把胜者提示词作为高质量样本 ──
    # 进化系统原本只能靠用户手动评分被动积累；这里把"对比胜出"视为
    # 一种隐式 5★ 反馈，主动喂给 prompt_evolution.image
    if prompts and winner_idx < len(prompts):
        winner_prompt = prompts[winner_idx]
        if winner_prompt:
            try:  # noqa: SIM105 — 回灌失败不影响主流程
                # 视为满分样本（对比胜出 ≈ 5/5）
                record_prompt_pair(
                    user_prompt=winner_prompt,
                    enhanced_prompt=winner_prompt,  # 对比场景没有"原始 vs 增强"
                    kind="image",
                    rating=5,
                )
            except (OSError, ValueError, TypeError, KeyError):
                pass  # 回灌失败不影响主流程

    return entry


def get_recent_comparisons(limit: int = 10) -> list[dict]:
    """获取最近 N 次对比记录（供 /compare 历史查看）"""
    mem = load_memory()
    return mem.get("comparisons", [])[:limit]


def get_comparison_stats() -> dict:
    """对比测试统计"""
    mem = load_memory()
    comps = mem.get("comparisons", [])
    return {
        "total": len(comps),
        "with_winner": sum(1 for c in comps if c.get("winner")),
    }


# ════════════════════════════════════════════════
#  Cross-Session Conversation Memory
# ════════════════════════════════════════════════

SESSION_FILE = _OUTPUT_DIR / "sessions.json"


def _ensure_session_file():
    if not SESSION_FILE.exists():
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sessions": {},
                    "user_profile": {},
                    "corrections": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


_SESSION_LOCK = threading.Lock()


def save_session(session_id: str, summary: str, messages: list[dict], task: str = ""):
    """Save a conversation session for cross-session recovery.

    Args:
        session_id: Unique session identifier
        summary: LLM-generated summary of the conversation
        messages: Full message history (will be truncated to save space)
        task: What the user was working on
    """
    _ensure_session_file()
    with _SESSION_LOCK:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))

        # Truncate messages to save space (keep last 10 + summary)
        truncated = []
        for msg in messages[-10:]:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
                )
            if isinstance(content, str) and len(content) > 500:
                content = content[:500] + "..."
            truncated.append(
                {
                    "role": msg.get("role", ""),
                    "content": content,
                }
            )

        data["sessions"][session_id] = {
            "summary": summary,
            "messages": truncated,
            "task": task,
            "saved_at": datetime.now().isoformat()[:19],
        }

        # Keep only last 20 sessions
        if len(data["sessions"]) > 20:
            sorted_keys = sorted(
                data["sessions"].keys(),
                key=lambda k: data["sessions"][k].get("saved_at", ""),
            )
            for old_key in sorted_keys[:-20]:
                del data["sessions"][old_key]

        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_session(session_id: str) -> dict:
    """Load a saved session by ID."""
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    return data.get("sessions", {}).get(session_id, {})


def get_recent_sessions(limit: int = 5) -> list[dict]:
    """Get recent sessions for recovery."""
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    sessions = data.get("sessions", {})
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get("saved_at", ""),
        reverse=True,
    )[:limit]
    return [{"id": sid, **info} for sid, info in sorted_sessions]


def get_session_context(session_id: str = "") -> str:
    """Get conversation context from a previous session.

    If session_id is empty, gets the most recent session.
    """
    if session_id:
        session = load_session(session_id)
    else:
        recent = get_recent_sessions(1)
        if not recent:
            return ""
        session = recent[0]

    if not session:
        return ""

    task = session.get("task", "")
    summary = session.get("summary", "")
    saved_at = session.get("saved_at", "")

    context = f"[Previous session - {saved_at}]\n"
    if task:
        context += f"Task: {task}\n"
    if summary:
        context += f"Summary: {summary}\n"
    return context


# ════════════════════════════════════════════════
#  User Profile - learn who the user is over time
# ════════════════════════════════════════════════


def update_user_profile(key: str, value: str):
    """Update a user profile field.

    Tracks information about the user: role, expertise, preferences,
    working style, common tasks, etc.
    """
    _ensure_session_file()
    with _SESSION_LOCK:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        data.setdefault("user_profile", {})

        # If key exists, append to history but keep latest as current
        profile = data["user_profile"].get(key, {})
        if not isinstance(profile, dict):
            profile = {"current": profile, "history": []}
        if "history" not in profile:
            profile["history"] = []

        if profile.get("current") != value:
            if profile.get("current"):
                profile["history"].append(
                    {
                        "value": profile["current"],
                        "until": datetime.now().isoformat()[:19],
                    }
                )
                profile["history"] = profile["history"][-10:]  # keep last 10
            profile["current"] = value
            profile["updated_at"] = datetime.now().isoformat()[:19]
            data["user_profile"][key] = profile
            SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_user_profile(key: str = "") -> dict | str:
    """Get user profile data."""
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    profile = data.get("user_profile", {})
    if key:
        entry = profile.get(key, {})
        return entry.get("current", "") if isinstance(entry, dict) else str(entry)
    return {k: v.get("current", v) if isinstance(v, dict) else v for k, v in profile.items()}


# ════════════════════════════════════════════════
#  Correction Memory - learn from user feedback
# ════════════════════════════════════════════════


def record_correction(what_happened: str, what_should_happen: str, context: str = ""):
    """Record a user correction for future learning.

    When the user says "no, don't do X, do Y instead", this saves
    the correction so the agent can avoid repeating the mistake.

    Deduplicates: skips if the same (context + what_happened) exists in last 3 entries.
    """
    _ensure_session_file()
    with _SESSION_LOCK:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        data.setdefault("corrections", [])

        # Dedup: skip if same context+what happened within last 3 entries
        recent = data["corrections"][:3]
        for r in recent:
            if r.get("context") == context and r["what_happened"][:80] == what_happened[:80]:
                return  # already recorded recently

        correction = {
            "what_happened": what_happened[:300],
            "what_should_happen": what_should_happen[:300],
            "context": context[:200],
            "at": datetime.now().isoformat()[:19],
        }
        data["corrections"].insert(0, correction)
        data["corrections"] = data["corrections"][:50]  # keep last 50
        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_corrections(limit: int = 10) -> list[dict]:
    """Get recent corrections for injection into system prompt."""
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    return data.get("corrections", [])[:limit]


def build_correction_context() -> str:
    """Build a context string from past corrections for the system prompt."""
    corrections = get_corrections(5)
    if not corrections:
        return ""
    lines = ["[Past corrections - avoid repeating these mistakes]"]
    for c in corrections:
        lines.append(f"- Don't: {c['what_happened'][:100]}")
        lines.append(f"  Do: {c['what_should_happen'][:100]}")
    return "\n".join(lines)


# ════════════════════════════════════════════════
#  Test Pattern Memory - learn from test failures across sessions
# ════════════════════════════════════════════════


def record_test_pattern(tool_name: str, failure_pattern: str, fix_applied: str):
    """Record a test failure pattern and the fix that worked.

    When a test loop fixes a failure, the pattern is saved so future
    test runs can reference past solutions for similar failures.

    Args:
        tool_name: The function or module being tested
        failure_pattern: Description of the failure (error message, assertion, etc.)
        fix_applied: The fix code or description that resolved the failure
    """
    _ensure_session_file()
    with _SESSION_LOCK:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        data.setdefault("test_patterns", [])

        pattern = {
            "tool": tool_name[:100],
            "failure": failure_pattern[:300],
            "fix": fix_applied[:500],
            "at": datetime.now().isoformat()[:19],
        }
        data["test_patterns"].insert(0, pattern)
        data["test_patterns"] = data["test_patterns"][:50]  # keep last 50
        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def build_test_context(tool_name: str = "") -> str:
    """Build a context string from past test patterns for the LLM.

    If tool_name is given, only returns patterns for that tool.
    Otherwise returns all recent patterns.

    Args:
        tool_name: Optional filter to only get patterns for a specific tool
    """
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    patterns = data.get("test_patterns", [])

    if tool_name:
        patterns = [p for p in patterns if tool_name.lower() in p.get("tool", "").lower()]

    if not patterns:
        return ""

    lines = ["[Past test patterns - reference these when fixing similar failures]"]
    for p in patterns[:5]:
        lines.append(f"- Tool: {p['tool']}")
        lines.append(f"  Failure: {p['failure'][:150]}")
        lines.append(f"  Fix that worked: {p['fix'][:200]}")
    return "\n".join(lines)


# ════════════════════════════════════════════════
#  Cross-session memory & tool learning
# ════════════════════════════════════════════════


def get_user_context() -> str:
    """Build a compact user memory injection for the system prompt."""
    parts = []
    raw_profile = get_user_profile()
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    if profile.get("role"):
        parts.append(f"用户角色: {profile['role']}")
    if profile.get("expertise"):
        parts.append(f"技术栈: {profile['expertise']}")
    if profile.get("language"):
        parts.append(f"语言偏好: {profile['language']}")
    corrections = get_corrections(3)
    if corrections:
        parts.append("历史纠正:")
        for c in corrections:
            parts.append(f"  不要: {c['what_happened'][:80]}")
            parts.append(f"  应该: {c['what_should_happen'][:80]}")
    return "\n".join(["[用户记忆]"] + parts) if parts else ""


def record_tool_learning(tool_name: str, failure: str, fix: str):
    """Record a tool failure and its fix for future learning."""
    _ensure_session_file()
    with _SESSION_LOCK:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        data.setdefault("tool_learnings", [])
        data["tool_learnings"].insert(
            0,
            {
                "tool": tool_name,
                "failure": failure[:200],
                "fix": fix[:200],
                "at": datetime.now().isoformat()[:19],
            },
        )
        data["tool_learnings"] = data["tool_learnings"][:30]
        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_tool_learnings(tool_name: str = "") -> str:
    """Get past tool learnings as context."""
    _ensure_session_file()
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    learnings = data.get("tool_learnings", [])
    if tool_name:
        learnings = [entry for entry in learnings if entry["tool"] == tool_name]
    if not learnings:
        return ""
    lines = [f"[{tool_name or '工具'}历史经验]"]
    for entry in learnings[:3]:
        lines.append(f"- 问题: {entry['failure'][:100]}")
        lines.append(f"  解法: {entry['fix'][:100]}")
    return "\n".join(lines)
