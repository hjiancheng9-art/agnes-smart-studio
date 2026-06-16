"""历史记录管理 - 生成记录、收藏、对比"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import OUTPUT_DIR

HISTORY_FILE = OUTPUT_DIR / "history.json"


def _ensure_history_file():
    if not HISTORY_FILE.exists():
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def load_history() -> list[dict]:
    """加载所有历史记录"""
    _ensure_history_file()
    with open(HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_history(records: list[dict]):
    """保存历史记录"""
    _ensure_history_file()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def add_record(
    record_type: str,
    prompt: str,
    model: str,
    result: dict,
    favorited: bool = False,
) -> dict:
    """添加一条生成记录"""
    records = load_history()
    entry = {
        "id": f"{record_type}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "type": record_type,
        "prompt": prompt,
        "model": model,
        "result": result,
        "favorited": favorited,
        "created_at": datetime.now().isoformat(),
    }
    records.insert(0, entry)
    save_history(records)
    return entry


def toggle_favorite(record_id: str) -> bool:
    """切换收藏状态"""
    records = load_history()
    for r in records:
        if r["id"] == record_id:
            r["favorited"] = not r.get("favorited", False)
            save_history(records)
            return r["favorited"]
    return False


def get_favorites() -> list[dict]:
    """获取收藏列表"""
    return [r for r in load_history() if r.get("favorited")]


def search_records(keyword: str) -> list[dict]:
    """按关键词搜索记录"""
    kw = keyword.lower()
    return [r for r in load_history() if kw in r.get("prompt", "").lower() or kw in r.get("model", "").lower()]


def delete_record(record_id: str) -> bool:
    """删除一条记录"""
    records = load_history()
    new_records = [r for r in records if r["id"] != record_id]
    if len(new_records) < len(records):
        save_history(new_records)
        return True
    return False
