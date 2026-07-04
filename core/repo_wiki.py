"""Repo Wiki 知识库 — 项目知识持久化与结构化检索

方法论第6章: 项目知识持久化、团队共享记忆、结构化索引、快速检索。
在 AGENTS.md + .crux_memory 基础上提供结构化知识库。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

WIKI_DIR = Path(".crux_wiki")
WIKI_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = WIKI_DIR / "_index.json"


def _load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {"pages": [], "categories": {}}


def _save_index(index: dict):
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def wiki_create(title: str, content: str, category: str = "general", tags: list[str] | None = None) -> dict:
    """Create a wiki page."""
    page_id = title.lower().replace(" ", "_").replace("/", "_")[:50]
    page = {
        "id": page_id,
        "title": title,
        "content": content,
        "category": category,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "word_count": len(content),
    }
    (WIKI_DIR / f"{page_id}.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")

    index = _load_index()
    if page_id not in index["pages"]:
        index["pages"].append(page_id)
    index["categories"].setdefault(category, []).append(page_id)
    _save_index(index)
    return page


def wiki_read(page_id: str) -> dict | None:
    """Read a wiki page by ID."""
    path = WIKI_DIR / f"{page_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def wiki_search(query: str, category: str | None = None) -> list[dict]:
    """Search wiki pages by keyword in title/content."""
    results = []
    query_lower = query.lower()
    for p in WIKI_DIR.glob("*.json"):
        if p.name == "_index.json":
            continue
        page = json.loads(p.read_text(encoding="utf-8"))
        if category and page.get("category") != category:
            continue
        if query_lower in page["title"].lower() or query_lower in page["content"].lower():
            results.append(
                {
                    "id": page["id"],
                    "title": page["title"],
                    "category": page["category"],
                    "snippet": page["content"][:200],
                }
            )
    return results


def wiki_list(category: str | None = None) -> list[dict]:
    """List all wiki pages."""
    results = []
    for p in sorted(WIKI_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == "_index.json":
            continue
        page = json.loads(p.read_text(encoding="utf-8"))
        if category and page.get("category") != category:
            continue
        results.append(
            {"id": page["id"], "title": page["title"], "category": page["category"], "tags": page.get("tags", [])}
        )
    return results


def wiki_delete(page_id: str) -> dict:
    """Delete a wiki page."""
    path = WIKI_DIR / f"{page_id}.json"
    if not path.exists():
        return {"error": f"Page {page_id} not found"}
    path.unlink()
    index = _load_index()
    if page_id in index["pages"]:
        index["pages"].remove(page_id)
    _save_index(index)
    return {"status": "deleted", "id": page_id}


# ── Knowledge import helpers ──


def wiki_import_from_memory() -> dict:
    """Import knowledge from .crux_memory into wiki."""
    memory_dir = Path(".crux_memory")
    if not memory_dir.exists():
        return {"status": "skipped", "reason": "No .crux_memory directory"}

    imported = 0
    for p in memory_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            title = data.get("title", p.stem)
            content = json.dumps(data, indent=2, ensure_ascii=False)
            wiki_create(title, content, category="imported", tags=["memory"])
            imported += 1
        except (json.JSONDecodeError, OSError):
            pass

    return {"status": "ok", "imported": imported}


# ── Tool Definitions ──

WIKI_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "wiki_create",
            "description": "Create a wiki page for persistent project knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "category": {"type": "string", "description": "e.g. architecture, decision, api, guide"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_read",
            "description": "Read a wiki page by ID.",
            "parameters": {"type": "object", "properties": {"page_id": {"type": "string"}}, "required": ["page_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "Search wiki pages by keyword.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "category": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_list",
            "description": "List all wiki pages.",
            "parameters": {"type": "object", "properties": {"category": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_import_from_memory",
            "description": "Import .crux_memory data into structured wiki.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

WIKI_EXECUTOR_MAP = {
    "wiki_create": lambda **kw: json.dumps(wiki_create(**kw), ensure_ascii=False),
    "wiki_read": lambda **kw: json.dumps(wiki_read(page_id=kw.get("page_id")), ensure_ascii=False),
    "wiki_search": lambda **kw: json.dumps(wiki_search(kw.get("query", ""), kw.get("category")), ensure_ascii=False),
    "wiki_list": lambda **kw: json.dumps(wiki_list(category=kw.get("category")), ensure_ascii=False),
    "wiki_import_from_memory": lambda **kw: json.dumps(wiki_import_from_memory(), ensure_ascii=False),
}
