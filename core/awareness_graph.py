"""#3 Qoder-style: Dynamic Awareness Knowledge Graph

Qoder 理念：记忆不是静态文件，而是会自修正的动态知识图谱。
从 awareness/ 三层结构（AGENTS.md / MEMORY.md / USER.md）中抽取
事实节点，构建可查询、可检测矛盾、可自动合并的知识网络。

核心能力：
- 解析 awareness/*.md → 实体/事实/会话节点
- 检测矛盾（两个事实声称不同版本号、不同状态等）
- 语义查询（"X 的版本是什么？"）
- 自动去重合并（同主题事实取最新时间戳）
- 导出为结构化 JSON 供其他模块消费
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "AwarenessGraph",
    "Fact",
    "Entity",
    "SessionNode",
    "Contradiction",
    "get_awareness_graph",
    "rebuild_awareness_graph",
]


ROOT = Path(__file__).resolve().parent.parent
AWARENESS_DIR = ROOT / "awareness"
MEMORY_DIR = AWARENESS_DIR / "memory"


# ── 数据模型 ──


@dataclass
class Fact:
    """A single extracted fact from awareness files."""

    key: str  # 规范化键，如 "qoder_cli_version", "os_name"
    raw_value: str  # 原始文本值
    category: str  # "env" | "decision" | "api" | "session" | "preference"
    source_file: str  # 来源文件相对路径
    line_number: int
    extracted_at: str = ""  # ISO 时间戳
    confidence: float = 1.0  # 0-1，解析可信度
    tags: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.key, self.raw_value, self.source_file))


@dataclass
class Entity:
    """An entity (person, tool, project) with its facts."""

    name: str
    facts: list[Fact] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    entity_type: str = "unknown"  # "person" | "tool" | "project" | "concept"

    @property
    def latest_fact(self) -> Fact | None:
        if not self.facts:
            return None
        return max(self.facts, key=lambda f: f.extracted_at or "")


@dataclass
class SessionNode:
    """A work session captured from memory files."""

    session_id: str  # 文件名如 "2026-06-25"
    title: str
    summary: str
    facts: list[Fact] = field(default_factory=list)
    date: str = ""


@dataclass
class Contradiction:
    """Two facts that conflict with each other."""

    entity: str
    key: str
    fact_a: Fact
    fact_b: Fact
    resolution: str = ""  # "keep_latest" | "keep_a" | "keep_b" | "unresolved"


# ── 解析器 ──


class AwarenessGraph:
    """Dynamic knowledge graph over awareness/ memory files.

    Parse → Extract → Detect Contradictions → Merge → Query.

    Usage:
        graph = get_awareness_graph()
        graph.rebuild()             # parse all files
        contradictions = graph.detect_contradictions()
        graph.resolve_contradictions(contradictions)  # auto-merge
        results = graph.query("Qoder CLI version")
    """

    def __init__(self, awareness_dir: Path | None = None) -> None:
        self._awareness_dir = awareness_dir or AWARENESS_DIR
        self._memory_dir = self._awareness_dir / "memory"
        self._entities: dict[str, Entity] = {}
        self._facts: list[Fact] = []
        self._sessions: list[SessionNode] = []
        self._contradictions: list[Contradiction] = []
        self._lock = threading.RLock()
        self._built = False

    # ── 解析 ──

    def rebuild(self) -> int:
        """Parse all awareness files and build the graph. Returns fact count."""
        with self._lock:
            self._entities.clear()
            self._facts.clear()
            self._sessions.clear()
            self._contradictions.clear()

            # 1. Parse MEMORY.md (facts and environment)
            memory_file = self._awareness_dir / "MEMORY.md"
            if memory_file.exists():
                self._parse_memory_md(memory_file)

            # 2. Parse AGENTS.md (conventions, rules)
            agents_file = self._awareness_dir / "AGENTS.md"
            if agents_file.exists():
                self._parse_agents_md(agents_file)

            # 3. Parse USER.md (preferences)
            user_file = self._awareness_dir / "USER.md"
            if user_file.exists():
                self._parse_user_md(user_file)

            # 4. Parse memory/*.md (session histories)
            if self._memory_dir.exists():
                for mem_file in sorted(self._memory_dir.glob("*.md")):
                    self._parse_session_file(mem_file)

            # 5. Build entities from facts
            self._build_entities()

            self._built = True
            return len(self._facts)

    def _parse_memory_md(self, path: Path) -> None:
        """Extract environment facts and decisions from MEMORY.md."""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        # Patterns: "- Key: value" or "- Key：value"
        env_pattern = re.compile(r"^-\s+(.+?)[：:]\s*(.+)$")
        section = "general"

        for i, line in enumerate(lines):
            if line.strip().startswith("## "):
                section = line.strip().lstrip("#").strip().lower()
                continue

            m = env_pattern.match(line)
            if m:
                key, value = m.group(1).strip(), m.group(2).strip()
                normalized_key = _normalize_key(key)
                category = self._section_to_category(section)
                fact = Fact(
                    key=normalized_key,
                    raw_value=value,
                    category=category,
                    source_file=str(path.relative_to(ROOT)),
                    line_number=i + 1,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                )
                self._facts.append(fact)

    def _parse_agents_md(self, path: Path) -> None:
        """Extract conventions and project rules from AGENTS.md."""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        # Extract bullet points as facts
        bullet_pattern = re.compile(r"^-\s+(.+)$")
        for i, line in enumerate(lines):
            m = bullet_pattern.match(line)
            if m:
                content = m.group(1).strip()
                # Skip markdown links and empty bullets
                if content.startswith("[") or len(content) < 5:
                    continue
                key = _normalize_key(content[:40])
                fact = Fact(
                    key=f"convention_{key}",
                    raw_value=content,
                    category="decision",
                    source_file=str(path.relative_to(ROOT)),
                    line_number=i + 1,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                )
                self._facts.append(fact)

    def _parse_user_md(self, path: Path) -> None:
        """Extract user preferences from USER.md."""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        pref_pattern = re.compile(r"^-\s+(.+?)[：:]\s*(.+)$")
        for i, line in enumerate(lines):
            m = pref_pattern.match(line)
            if m:
                key, value = m.group(1).strip(), m.group(2).strip()
                fact = Fact(
                    key=f"pref_{_normalize_key(key)}",
                    raw_value=value,
                    category="preference",
                    source_file=str(path.relative_to(ROOT)),
                    line_number=i + 1,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                )
                self._facts.append(fact)

    def _parse_session_file(self, path: Path) -> None:
        """Parse a session memory file."""
        text = path.read_text(encoding="utf-8")
        session_id = path.stem

        # Extract title
        title_match = re.search(r"##\s+Session:\s*(.+)", text)
        title = title_match.group(1).strip() if title_match else session_id

        # Extract summary (first paragraph after title)
        summary = ""
        lines = text.split("\n")
        in_content = False
        for line in lines:
            if line.strip().startswith("## Session:"):
                in_content = True
                continue
            if (in_content and line.strip() and not line.strip().startswith("#")
                    and not line.strip().startswith("<!--")
                    and not line.strip().startswith("-")):
                summary = line.strip()
                break

        # Extract fact-like lines
        fact_pattern = re.compile(r"^-\s+(.+?)[：:]\s*(.+)$")
        facts: list[Fact] = []
        for i, line in enumerate(lines):
            m = fact_pattern.match(line)
            if m:
                key, value = m.group(1).strip(), m.group(2).strip()
                fact = Fact(
                    key=_normalize_key(key),
                    raw_value=value,
                    category="session",
                    source_file=str(path.relative_to(ROOT)),
                    line_number=i + 1,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                )
                facts.append(fact)
                self._facts.append(fact)

        session = SessionNode(
            session_id=session_id,
            title=title,
            summary=summary,
            facts=facts,
            date=session_id,
        )
        self._sessions.append(session)

    def _build_entities(self) -> None:
        """Cluster facts into entities."""
        entity_map: dict[str, list[Fact]] = defaultdict(list)

        for fact in self._facts:
            # Derive entity name from key prefix
            prefix = fact.key.split("_")[0] if "_" in fact.key else fact.key[:10]
            entity_map[prefix].append(fact)

        for name, facts in entity_map.items():
            entity = Entity(name=name, facts=facts)
            self._entities[name] = entity

    # ── 矛盾检测 ──

    def detect_contradictions(self) -> list[Contradiction]:
        """Find conflicting facts (same key, different values)."""
        self._contradictions.clear()
        by_key: dict[str, list[Fact]] = defaultdict(list)

        for fact in self._facts:
            by_key[fact.key].append(fact)

        for key, facts in by_key.items():
            if len(facts) < 2:
                continue
            # Group by value
            by_value: dict[str, list[Fact]] = defaultdict(list)
            for f in facts:
                by_value[f.raw_value.strip().lower()].append(f)

            if len(by_value) > 1:
                # Conflict found
                values = list(by_value.values())
                for i in range(len(values) - 1):
                    for j in range(i + 1, len(values)):
                        fact_a = values[i][0]
                        fact_b = values[j][0]
                        # Determine entity
                        prefix = key.split("_")[0] if "_" in key else key[:10]
                        contradiction = Contradiction(
                            entity=prefix,
                            key=key,
                            fact_a=fact_a,
                            fact_b=fact_b,
                            resolution="unresolved",
                        )
                        self._contradictions.append(contradiction)

        return self._contradictions

    def resolve_contradictions(self, strategy: str = "keep_latest") -> list[Contradiction]:
        """Auto-resolve contradictions using the given strategy.

        Strategies:
            - "keep_latest": keep the fact from the most recent source file
            - "keep_most_common": keep the value that appears most often
            - "mark_unresolved": don't resolve, just mark (default)
        """
        if not self._contradictions:
            self.detect_contradictions()

        for c in self._contradictions:
            if strategy == "keep_latest":
                # Pick fact from newer source (by filename date)
                a_date = _extract_date(c.fact_a.source_file)
                b_date = _extract_date(c.fact_b.source_file)
                winner = c.fact_a if a_date >= b_date else c.fact_b
                c.resolution = f"keep_latest: {winner.raw_value}"
                # Update other facts' confidence
                loser = c.fact_b if winner is c.fact_a else c.fact_a
                loser.confidence = 0.3

            elif strategy == "keep_most_common":
                by_key: dict[str, list[Fact]] = defaultdict(list)
                for f in self._facts:
                    if f.key == c.key:
                        by_key[f.raw_value.strip().lower()].append(f)
                most_common = max(by_key.values(), key=len)[0]
                c.resolution = f"keep_most_common: {most_common.raw_value}"

            else:
                c.resolution = "unresolved"

        return self._contradictions

    # ── 查询 ──

    def query(self, query_str: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search over the knowledge graph.

        Matches against fact keys, raw values, entity names, and session titles.
        Returns ranked results with relevance scores.
        """
        if not self._built:
            self.rebuild()

        query_lower = query_str.lower()
        query_tokens = set(query_lower.split())
        results: list[tuple[float, dict]] = []

        # Match facts
        for fact in self._facts:
            text = f"{fact.key} {fact.raw_value} {fact.category} {' '.join(fact.tags)}".lower()
            score = _tfidf_score(query_tokens, text)
            if score > 0:
                results.append((score, {
                    "type": "fact",
                    "key": fact.key,
                    "value": fact.raw_value,
                    "category": fact.category,
                    "source": fact.source_file,
                    "confidence": fact.confidence,
                    "score": round(score, 3),
                }))

        # Match entities
        for name, entity in self._entities.items():
            if query_lower in name.lower():
                results.append((0.9, {
                    "type": "entity",
                    "name": name,
                    "fact_count": len(entity.facts),
                    "entity_type": entity.entity_type,
                    "score": 0.9,
                }))

        # Match sessions
        for session in self._sessions:
            text = f"{session.title} {session.summary}".lower()
            score = _tfidf_score(query_tokens, text)
            if score > 0:
                results.append((score, {
                    "type": "session",
                    "session_id": session.session_id,
                    "title": session.title,
                    "summary": session.summary,
                    "date": session.date,
                    "score": round(score, 3),
                }))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:top_k]]

    def get_fact(self, key: str) -> Fact | None:
        """Look up a fact by its normalized key."""
        for fact in self._facts:
            if fact.key == key:
                return fact
        return None

    def get_entity(self, name: str) -> Entity | None:
        """Get or create an entity by name."""
        return self._entities.get(name)

    def get_session(self, session_id: str) -> SessionNode | None:
        """Get a session by ID."""
        for s in self._sessions:
            if s.session_id == session_id:
                return s
        return None

    # ── 统计 ──

    @property
    def stats(self) -> dict:
        return {
            "facts": len(self._facts),
            "entities": len(self._entities),
            "sessions": len(self._sessions),
            "contradictions": len(self._contradictions),
            "built": self._built,
        }

    def export(self) -> dict:
        """Export the full graph as a JSON-serializable dict."""
        return {
            "stats": self.stats,
            "entities": {name: asdict(e) for name, e in self._entities.items()},
            "sessions": [asdict(s) for s in self._sessions],
            "contradictions": [asdict(c) for c in self._contradictions],
        }

    @staticmethod
    def _section_to_category(section: str) -> str:
        mapping = {
            "环境": "env",
            "environment": "env",
            "关键决策": "decision",
            "key decisions": "decision",
            "decisions": "decision",
            "api 端点": "api",
            "api endpoints": "api",
            "preferences": "preference",
            "偏好": "preference",
        }
        return mapping.get(section.lower(), "general")


# ── 辅助函数 ──


def _normalize_key(raw: str) -> str:
    """Normalize a fact key: lowercase, replace spaces/symbols with _."""
    key = raw.lower().strip()
    key = re.sub(r"[：:\-\s]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    return key[:80]  # cap length


def _extract_date(path_str: str) -> str:
    """Extract a date string from a file path (e.g., '2026-06-25')."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path_str)
    return m.group(1) if m else "0000-00-00"


def _tfidf_score(query_tokens: set[str], text: str) -> float:
    """Simple TF-IDF-like score for a text against query tokens."""
    if not query_tokens:
        return 0.0
    doc_tokens = set(text.split())
    if not doc_tokens:
        return 0.0
    overlap = query_tokens & doc_tokens
    # TF component: how many query tokens are in the doc
    tf = len(overlap) / len(query_tokens)
    # IDF component: the rarer the token, the more valuable
    idf_sum = sum(1.0 / (1 + text.count(t)) for t in overlap)
    return tf * (idf_sum / max(len(overlap), 1))


# ── 全局单例 ──

_graph: AwarenessGraph | None = None
_graph_lock = threading.RLock()


def get_awareness_graph() -> AwarenessGraph:
    """Get or create the global awareness graph singleton (lazy build)."""
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                _graph = AwarenessGraph()
                _graph.rebuild()
    return _graph


def rebuild_awareness_graph() -> AwarenessGraph:
    """Force rebuild the global awareness graph."""
    global _graph
    with _graph_lock:
        _graph = AwarenessGraph()
        _graph.rebuild()
    return _graph
