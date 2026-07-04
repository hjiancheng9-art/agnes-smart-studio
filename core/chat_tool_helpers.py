"""Tool call helpers — extracted from chat.py.

Pure functions for merging, normalizing, and sanitizing tool calls.
No ChatSession dependency — usable by both sync and async sessions.
"""
from __future__ import annotations

import json

_sanitize_cache: tuple[int, int, list[dict]] = (0, 0, [])

def normalize_tool_args(args_json: str) -> str:
    """归一化工具 arguments JSON 字符串，用于语义去重签名。

    解析 JSON → 按 key 排序 → 紧凑序列化，使 {"a":1,"b":2} 与 {"b":2,"a":1}
    产生相同签名。解析失败时退化为去空白原串（仍能去重明显重复）。
    """
    s = (args_json or '').strip()
    if not s:
        return ''
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return json.dumps(parsed, sort_keys=True, separators=(',', ':'))
        return json.dumps(parsed, sort_keys=True, separators=(',', ':'))
    except (json.JSONDecodeError, TypeError):
        return ''.join(s.split())

def merge_tool_calls(fragments: list[dict]) -> list[dict]:
    """合并流式 tool_calls 分片（按 index 聚合 name + arguments 字符串）。

    OpenAI 流式把一个 tool_call 拆成多个 delta。
    推理模型可能跨思考/回答阶段对同一工具发不同 index 分片，
    故追加语义去重：相同 (name, normalized_arguments) 只保留首个。
    """
    merged: dict[int, dict] = {}
    for frag in fragments:
        idx = frag.get('index', 0)
        slot = merged.setdefault(idx, {'id': frag.get('id', ''), 'type': 'function', 'function': {'name': '', 'arguments': ''}})
        if frag.get('id'):
            slot['id'] = frag['id']
        fn = frag.get('function', {}) or {}
        if fn.get('name'):
            slot['function']['name'] += fn['name']
        if fn.get('arguments'):
            slot['function']['arguments'] += fn['arguments']
    ordered = [merged[k] for k in sorted(merged.keys())]
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for entry in ordered:
        name = (entry.get('function', {}).get('name') or '').strip()
        args_raw = entry.get('function', {}).get('arguments', '') or ''
        sig = (name, normalize_tool_args(args_raw))
        if not name or sig in seen:
            continue
        seen.add(sig)
        deduped.append(entry)
    return deduped

def sanitize_tool_call_history(messages: list[dict]) -> list[dict]:
    """清洗消息历史中的孤儿 tool_calls，保证发给 API 的消息始终合法。

    OpenAI 兼容 API 要求:含 tool_calls 的 assistant 消息后面必须有对应
    数量的 role=tool 消息。若缺失配对 → API 返回 400。
    使用模块级缓存避免重复深拷贝。
    """
    global _sanitize_cache
    if not messages:
        return messages
    current_id = id(messages)
    current_len = len(messages)
    cache_id, cache_len, cache_result = _sanitize_cache
    if current_id == cache_id and current_len == cache_len:
        return cache_result
    result = [dict(m) for m in messages]
    assistant_indices: list[int] = []
    for i, msg in enumerate(result):
        if msg.get('role') == 'assistant' and msg.get('tool_calls'):
            assistant_indices.append(i)
    tool_ids_from_assistant: dict[int, set[str]] = {}
    for ai in assistant_indices:
        tc_ids = {tc.get('id', '') for tc in result[ai].get('tool_calls', []) if tc.get('id')}
        tool_ids_from_assistant[ai] = tc_ids
    tool_msg_indices: list[int] = []
    tool_msg_matched_to: dict[int, int] = {}
    unmatched_tool_indices: set[int] = set()
    for i, msg in enumerate(result):
        if msg.get('role') == 'tool':
            tool_msg_indices.append(i)
            tcid = msg.get('tool_call_id', '')
            matched = False
            for ai in assistant_indices:
                if ai >= i:
                    break
                if tcid in tool_ids_from_assistant.get(ai, set()):
                    tool_msg_matched_to[i] = ai
                    tool_ids_from_assistant[ai].discard(tcid)
                    matched = True
                    break
            if not matched:
                unmatched_tool_indices.add(i)
    for i in sorted(unmatched_tool_indices, reverse=True):
        result.pop(i)
        for k in list(tool_msg_matched_to.keys()):
            if k > i:
                tool_msg_matched_to[k] = tool_msg_matched_to[k]
    for k in list(tool_msg_indices):
        if k >= len(result):
            tool_msg_indices.remove(k)
    for ai in sorted(assistant_indices, reverse=True):
        if ai >= len(result):
            continue
        remaining = tool_ids_from_assistant.get(ai, set())
        if remaining:
            result[ai] = dict(result[ai])
            tcs = result[ai].get('tool_calls', [])
            result[ai]['tool_calls'] = [tc for tc in tcs if tc.get('id', '') not in remaining]
    for i in range(len(result)):
        if result[i].get('role') == 'assistant' and result[i].get('tool_calls') == []:
            del result[i]['tool_calls']
    _sanitize_cache = (current_id, current_len, result)
    return result
