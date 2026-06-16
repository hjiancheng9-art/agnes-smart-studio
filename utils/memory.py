"""学习记忆模块 - 记录用户偏好、生成反馈、自动优化

数据文件：
  output/memory.json   - 偏好与学习数据
  output/history.json  - 生成记录（含评分）
"""

import json
import os
from datetime import datetime
from pathlib import Path
from core.config import OUTPUT_DIR

MEMORY_FILE = OUTPUT_DIR / "memory.json"


def _ensure_file():
    if not MEMORY_FILE.exists():
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps({
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "preferences": {},
            "ratings": {},
            "stats": {"total": 0, "image": 0, "video": 0, "pipeline": 0,
                      "avg_image_rating": 0, "avg_video_rating": 0,
                      "content_policy_hits": 0},
            "patterns": [],
            "tips_shown": [],
        }, indent=2, ensure_ascii=False), encoding="utf-8")


def load_memory() -> dict:
    _ensure_file()
    return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))


def save_memory(data: dict):
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── 偏好学习 ─────────────────────────────────────────

def record_preference(key: str, value):
    """记录用户偏好设置（自动去重、频率计数）"""
    mem = load_memory()
    prefs = mem.setdefault("preferences", {})
    if key not in prefs:
        prefs[key] = {"values": {}, "last_used": None}
    val_str = str(value)
    prefs[key]["values"][val_str] = prefs[key]["values"].get(val_str, 0) + 1
    prefs[key]["last_used"] = val_str
    save_memory(mem)


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
    mem = load_memory()
    mem.setdefault("ratings", {})[record_id] = {
        "rating": max(1, min(5, rating)),
        "rated_at": datetime.now().isoformat(),
    }
    # 同步更新 history.json 中的评分
    _sync_rating_to_history(record_id, rating)
    _update_stats(mem)
    save_memory(mem)


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
    mem = load_memory()
    mem.setdefault("stats", {})
    mem["stats"]["total"] = mem["stats"].get("total", 0) + 1

    # 按类型统计
    type_key = kind.split("_")[0]  # text_to_image → text, image_to_video → image
    if "image" in kind:
        mem["stats"]["image"] = mem["stats"].get("image", 0) + 1
    if "video" in kind:
        mem["stats"]["video"] = mem["stats"].get("video", 0) + 1

    # 提取关键词模式
    keywords = _extract_keywords(prompt)
    if keywords:
        mem.setdefault("patterns", [])
        mem["patterns"].append({"prompt": prompt[:120], "keywords": keywords,
                                "kind": kind, "at": datetime.now().isoformat()[:19]})
        # 只保留最近 50 条
        mem["patterns"] = mem["patterns"][-50:]

    save_memory(mem)


def track_content_policy_hit(prompt: str):
    """追踪内容过滤触发"""
    mem = load_memory()
    mem["stats"]["content_policy_hits"] = mem["stats"].get("content_policy_hits", 0) + 1
    save_memory(mem)


def _extract_keywords(prompt: str) -> list[str]:
    """提取用户常用的关键词"""
    # 简单按空格/逗号分割取前几个词
    try:
        # 尝试用 jieba（如果安装了），否则用简单分割
        import jieba
        words = [w.strip() for w in jieba.cut(prompt) if len(w.strip()) > 1]
    except ImportError:
        words = [w.strip() for w in prompt.replace("，", ",").replace("、", " ").split()
                 if len(w.strip()) > 1]
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
    mem = load_memory()
    mem.setdefault("tips_shown", [])
    if tip_id not in mem["tips_shown"]:
        mem["tips_shown"].append(tip_id)
        save_memory(mem)


# ════════════════════════════════════════════════
#  Prompt 进化系统 — 通过评分反馈持续优化增强效果
# ════════════════════════════════════════════════

def record_prompt_pair(user_prompt: str, enhanced_prompt: str, kind: str,
                       rating: int, record_id: str = ""):
    """记录一组 (原始提示词, 增强后提示词, 评分) 用于进化学习

    kind: "image" 或 "video"
    高分(4-5)的记录会被作为"成功案例"用于后续优化参考
    """
    if rating < 3:  # 低分不记录，避免污染样本
        return
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
    save_memory(mem)


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
