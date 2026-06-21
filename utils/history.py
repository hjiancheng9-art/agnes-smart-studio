"""历史记录管理 - 生成记录、收藏、对比

存储优化（解决"卡壳"根因之一）：
- 增量写 JSONL（每条一行），避免每次全量读写整个文件
- 写入前剥离 result 中的大字段（base64 图片/视频），只保留元数据
- 自动从旧 history.json 迁移并瘦身（9MB+ → 数百 KB）
- 所有公开函数签名保持不变，调用点无需改动
"""

import json
from datetime import datetime

from core.config import OUTPUT_DIR
import contextlib

__all__ = [
    'HISTORY_FILE', 'HISTORY_JSONL', 'add_record', 'delete_record', 'get_favorites', 'load_history', 'save_history', 'search_records', 'toggle_favorite',
]


# 旧格式：单个大 JSON 数组（全量读写，膨胀严重）
HISTORY_FILE = OUTPUT_DIR / "history.json"
# 新格式：每条记录一行的 JSONL（增量追加，O(1)）
HISTORY_JSONL = OUTPUT_DIR / "history.jsonl"

# result 中需要剥离的大字段（base64 / 原始二进制数据）
_HEAVY_FIELDS = {"b64_json", "image", "data", "base64", "url"}
# 瘦身后保留的字段（其余大字段截断或丢弃）
_KEEP_RESULT_KEYS = {
    "local_path", "remote_url", "prompt", "model", "size", "status",
    "progress", "seed", "negative_prompt", "video_id", "error",
    "width", "height", "num_frames", "frame_rate", "duration_seconds",
}
# 长字符串字段截断阈值
_MAX_STR_LEN = 200


def _ensure_files():
    """确保存储目录存在。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _slim_result(result):
    """剥离 result 中的大字段，只保留可读元数据。

    原历史记录把 base64 图片/完整响应塞进 result，导致单条 100KB+。
    这里只保留 local_path / status / prompt 等轻量字段，
    对长字符串字段做截断，使单条记录稳定在 1KB 量级。
    """
    if not isinstance(result, dict):
        # 非 dict（少见）：若过长则截断
        if isinstance(result, str) and len(result) > _MAX_STR_LEN:
            return result[:_MAX_STR_LEN] + "...[truncated]"
        return result

    slimmed = {}
    # 1. 白名单字段直接取
    for k in _KEEP_RESULT_KEYS:
        if k in result:
            v = result[k]
            if isinstance(v, str) and len(v) > _MAX_STR_LEN:
                slimmed[k] = v[:_MAX_STR_LEN] + "...[truncated]"
            else:
                slimmed[k] = v
    # 2. images 列表：保留路径，丢弃 base64
    if "images" in result and isinstance(result["images"], list):
        imgs = []
        for item in result["images"]:
            if isinstance(item, dict):
                p = item.get("local_path") or item.get("path")
                if p:
                    imgs.append({"local_path": p})
            elif isinstance(item, str):
                imgs.append({"local_path": item})
        if imgs:
            slimmed["images"] = imgs
    # 3. variants / frames 同理只留路径
    for list_key in ("variants", "frames"):
        if list_key in result and isinstance(result[list_key], list):
            paths = []
            for item in result[list_key]:
                if isinstance(item, dict):
                    p = item.get("local_path") or item.get("path")
                    if p:
                        paths.append(p)
            if paths:
                slimmed[list_key] = paths
    # 4. 显式丢弃已知的重型字段（即便不在白名单，也确保不泄漏）
    for heavy in _HEAVY_FIELDS:
        slimmed.pop(heavy, None)
    return slimmed


def _migrate_legacy_if_needed():
    """一次性迁移：把旧 history.json（全量大数组）转为 JSONL 并瘦身。

    迁移后旧文件改名为 history.json.bak 保留，不会删除用户数据。
    幂等：JSONL 已存在则跳过迁移。

    原子性保证：先写入 .tmp 文件并 flush，确认完整后再 rename 成
    .jsonl，最后才 rename 旧文件为 .bak。任意中间步骤崩溃都不会
    让 JSONL 处于半成品状态而旧数据已丢失。
    """
    if HISTORY_JSONL.exists():
        return
    if not HISTORY_FILE.exists():
        return
    tmp = HISTORY_JSONL.with_suffix(".jsonl.tmp")
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            return
        _ensure_files()
        # 1. 先写临时文件，写完 flush+os.fsync 落盘
        with open(tmp, "w", encoding="utf-8") as out:
            for r in records:
                if not isinstance(r, dict):
                    continue
                # 迁移时同样瘦身 result
                if "result" in r:
                    r["result"] = _slim_result(r["result"])
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
            try:
                import os as _os
                _os.fsync(out.fileno())
            except OSError:
                pass
        # 2. 原子 rename：tmp → jsonl（成功后 JSONL 才正式存在）
        tmp.replace(HISTORY_JSONL)
        # 3. JSONL 已就位，旧文件保留为 .bak（此步失败不影响数据完整性）
        bak = HISTORY_FILE.with_suffix(".json.bak")
        with contextlib.suppress(OSError):
            HISTORY_FILE.rename(bak)
    except (json.JSONDecodeError, OSError):
        # 清理半成品临时文件，下次启动可重试迁移
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _read_jsonl() -> list[dict]:
    """读取全部记录（按写入顺序倒序返回，最新在前）。"""
    _migrate_legacy_if_needed()
    if not HISTORY_JSONL.exists():
        return []
    records = []
    try:
        with open(HISTORY_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    # JSONL 末尾追加 = 最新；展示时最新在前
    records.reverse()
    return records


def _rewrite_jsonl(records: list[dict]):
    """全量重写 JSONL（用于删除/收藏等小规模变更）。"""
    _ensure_files()
    # 写临时文件再替换，避免中途崩溃损坏数据
    tmp = HISTORY_JSONL.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        # records 最新在前；JSONL 存储顺序无关，统一写入即可
        for r in records:
            try:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except (TypeError, ValueError):
                continue
    # Windows 上若目标文件被其他进程占用，replace 会抛 PermissionError；
    # 此时回退为直接覆盖写，保证收藏/删除等操作不致彻底失败。
    try:
        tmp.replace(HISTORY_JSONL)
    except OSError:
        try:
            with open(HISTORY_JSONL, "w", encoding="utf-8") as f:
                for r in records:
                    try:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    except (TypeError, ValueError):
                        continue
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass


def load_history() -> list[dict]:
    """加载所有历史记录（最新在前）。"""
    return _read_jsonl()


def save_history(records: list[dict]):
    """保存历史记录（全量覆写，用于兼容旧调用点）。

    内部走 JSONL 全量重写。普通新增请用 add_record（增量追加）。
    """
    _rewrite_jsonl(records)


def add_record(
    record_type: str,
    prompt: str,
    model: str,
    result: dict,
    favorited: bool = False,
) -> dict:
    """添加一条生成记录（增量追加，O(1)）。"""
    _ensure_files()
    _migrate_legacy_if_needed()
    entry = {
        "id": f"{record_type}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "type": record_type,
        "prompt": prompt,
        "model": model,
        "result": _slim_result(result),
        "favorited": favorited,
        "created_at": datetime.now().isoformat(),
    }
    # 追加写一行，不再读/写整个文件
    try:
        with open(HISTORY_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
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
    return [r for r in load_history()
            if kw in r.get("prompt", "").lower() or kw in r.get("model", "").lower()]


def delete_record(record_id: str) -> bool:
    """删除一条记录"""
    records = load_history()
    new_records = [r for r in records if r["id"] != record_id]
    if len(new_records) < len(records):
        save_history(new_records)
        return True
    return False
