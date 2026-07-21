"""腰带 · 流式数据管线 — unified streaming stack.
Chains: source → transform → filter → buffer → sink.
All tool output flows through this pipeline, enabling:
  - real-time streaming to Rich terminal
  - buffering for batch flush to disk
  - filtering sensitive data before log
Usage: from core.intimate_slots.belt import pipeline
pipeline.push(data)
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclass
class StreamStage:
    name: str
    handler: Callable[[Any], Any]
    enabled: bool = True


class DataPipeline:
    def __init__(self, max_buffer: int = 500):
        self._stages: list[StreamStage] = []
        self._buffer: deque = deque(maxlen=max_buffer)
        self._flush_interval = 5.0
        self._last_flush = time.time()

    def add_stage(self, name: str, handler: Callable[[Any], Any]):
        self._stages.append(StreamStage(name=name, handler=handler))

    def push(self, data: Any, event: str = ""):
        """Push data through all stages, then buffer."""
        item = {"data": data, "event": event, "ts": time.time()}
        for stage in self._stages:
            if stage.enabled:
                with contextlib.suppress(Exception):
                    item["data"] = stage.handler(item["data"])
        self._buffer.append(item)

    def flush(self):
        """Flush buffer to disk log."""
        if not self._buffer:
            return
        try:
            from pathlib import Path

            log_path = Path(__file__).resolve().parent.parent.parent / "output" / "stream_log.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                import json

                for item in self._buffer:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._buffer.clear()
            self._last_flush = time.time()
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("Belt flush: %s", e)

    def auto_flush(self):
        if time.time() - self._last_flush >= self._flush_interval:
            self.flush()

    def summary(self) -> str:
        stages = [s.name for s in self._stages if s.enabled]
        return f"[腰带] {len(stages)} stages: {', '.join(stages)} | buffer: {len(self._buffer)}"


pipeline = DataPipeline()
