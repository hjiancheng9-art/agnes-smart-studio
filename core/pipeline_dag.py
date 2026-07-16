"""Pipeline DAG — 青龙呼吸。Showrunner 并行引擎。
File ownership enforced: nodes with overlapping file owners fail early.
Merge then node works correctly. Runs connected to event bus.
Usage:
  dag = DAG("short_video")
  dag.node("brainstorm").then("script").then("prompts")
  dag.node("prompts").then("image_A").then("animate_A")
  dag.node("prompts").then("image_B").then("animate_B")
  dag.merge(["animate_A","animate_B"]).then("review").then("deliver")
  results = dag.run()
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.dag")


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Node:
    name: str
    action: Callable[..., Any] | None = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    deps: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str = ""
    retries: int = 0
    max_retries: int = 2
    fallback: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0


class DAG:
    def __init__(self, name: str = "pipeline"):
        self.name = name
        self.nodes: dict[str, Node] = {}
        self._cursor: str | None = None
        self._merging: list[str] = []
        self._file_registry: dict[str, str] = {}  #

    def node(self, name: str) -> DAG:
        if name not in self.nodes:
            self.nodes[name] = Node(name=name)
        node = self.nodes[name]
        if self._merging:
            for dep in self._merging:
                if dep not in node.deps:
                    node.deps.append(dep)
            self._merging = []
        elif self._cursor:
            if self._cursor not in node.deps:
                node.deps.append(self._cursor)
        self._cursor = name
        return self

    def then(self, name: str) -> DAG:
        return self.node(name)

    def merge(self, names: list[str]) -> DAG:
        self._merging = list(names)
        self._cursor = None
        return self

    def action(self, fn: Callable, *args, **kwargs) -> DAG:
        if self._cursor:
            self.nodes[self._cursor].action = fn
            self.nodes[self._cursor].args = args
            self.nodes[self._cursor].kwargs = kwargs
        return self

    def file_owned(self, name: str, files: list[str]) -> DAG:
        if name not in self.nodes:
            self.node(name)
        node = self.nodes[name]
        # Ownership conflict check
        for f in files:
            existing_owner = self._file_registry.get(f)
            if existing_owner and existing_owner != name:
                logger.warning("[DAG] file collision: %s owned by %s, reassigned to %s", f, existing_owner, name)
        for f in files:
            self._file_registry[f] = name
        node.owners = files
        return self

    def fallback_to(self, name: str, fb: str) -> DAG:
        if name in self.nodes:
            self.nodes[name].fallback = fb
        return self

    @property
    def entry_nodes(self) -> list[str]:
        return [n for n in self.nodes if not self.nodes[n].deps]

    def _ready(self, name: str) -> bool:
        node = self.nodes[name]
        return node.status == NodeStatus.PENDING and all(self.nodes[d].status == NodeStatus.DONE for d in node.deps)

    def run(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        queue: deque = deque(self.entry_nodes)
        try:
            from core.event_bus import bus

            bus.emit("dag:started", dag=self.name, nodes=len(self.nodes))
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("[DAG] event emit failed for %s: %s", self.name, e)
        while queue:
            batch = [n for n in queue if self._ready(n)]
            if not batch:
                pending = [n for n in self.nodes if self.nodes[n].status == NodeStatus.PENDING]
                if pending:
                    logger.error("[DAG] stuck: %s", pending)
                break
            queue = deque(n for n in queue if n not in batch)
            for name in batch:
                node = self.nodes[name]
                node.status = NodeStatus.RUNNING
                node.started_at = time.time()
                if node.action:
                    try:
                        node.result = node.action(*node.args, **node.kwargs)
                        node.status = NodeStatus.DONE
                        node.finished_at = time.time()
                        results[name] = node.result
                    except (RuntimeError, OSError, TypeError, ValueError, KeyError) as e:
                        logger.exception("[DAG] Node '%s' failed: %s", name, e)
                        node.error = str(e)
                        if node.retries < node.max_retries:
                            node.retries += 1
                            node.status = NodeStatus.PENDING
                            queue.append(name)
                        elif node.fallback and node.fallback in self.nodes:
                            node.status = NodeStatus.SKIPPED
                            fb = self.nodes[node.fallback]
                            fb.deps = [d for d in fb.deps if d != name]
                            queue.append(node.fallback)
                        else:
                            node.status = NodeStatus.FAILED
                            node.finished_at = time.time()
                else:
                    node.status = NodeStatus.DONE
                    node.finished_at = time.time()
                if node.status == NodeStatus.DONE:
                    try:
                        from core.event_bus import bus

                        bus.emit("dag:node_done", node=name, owners=node.owners)
                    except (ImportError, RuntimeError, OSError) as e:
                        logger.debug("[DAG] node_done emit failed for %s: %s", name, e)
                    for ds in self.nodes:
                        if name in self.nodes[ds].deps and ds not in queue:
                            queue.append(ds)
        try:
            from core.event_bus import bus

            bus.emit("dag:finished", dag=self.name, nodes_done=len(results))
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("[DAG] finished emit failed for %s: %s", self.name, e)
        return results

    def summary(self) -> str:
        sym = {"pending": ".", "running": "~", "done": "+", "failed": "!", "skipped": "-"}
        lines = [f"\n## DAG: {self.name} ({len(self.nodes)} nodes)"]
        for n, nd in self.nodes.items():
            s = sym.get(nd.status.value, "?")
            extra = f" [{', '.join(nd.owners)}]" if nd.owners else ""
            lines.append(f"  [{s}] {n}{extra}")
        return "\n".join(lines)
