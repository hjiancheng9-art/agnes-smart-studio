"""Lightweight observability: tracing, spans, and metrics for the agent runtime."""

import contextvars
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import OUTPUT_DIR

# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

__all__ = [
    "Metrics", "Span", "TraceContext", "Tracer", "get_recent_traces", "metrics", "tracer",
]
@dataclass
class Span:
    """A single unit of work within a trace."""

    span_id: str
    trace_id: str
    parent_id: str
    name: str
    start_time: float
    end_time: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def duration_ms(self) -> float:
        """Return duration in milliseconds (0 if not yet finished)."""
        if self.end_time == 0.0:
            return 0.0
        return (self.end_time - self.start_time) * 1000.0

    def finish(self, status: str = "ok") -> None:
        """Mark the span as finished."""
        self.end_time = time.time()
        self.status = status

    def set_attribute(self, key: str, value: Any) -> None:
        """Add or update an attribute on this span."""
        self.attributes[key] = value

    def add_event(self, name: str, **kwargs: Any) -> None:
        """Append a timestamped event to this span."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            **kwargs,
        })


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class Tracer:
    """Creates spans and writes them to a JSONL log file."""

    def __init__(self, log_file: str | None = None) -> None:
        if log_file is None:
            self._log_file: Path = OUTPUT_DIR / "traces.jsonl"
        else:
            self._log_file = Path(log_file)
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._current_trace_id: str = ""

    # -- trace / span creation -------------------------------------------------

    def start_trace(self, name: str) -> Span:
        """Create a root span that starts a new trace."""
        trace_id = uuid.uuid4().hex[:16]
        self._current_trace_id = trace_id
        return Span(
            span_id=uuid.uuid4().hex[:12],
            trace_id=trace_id,
            parent_id="",
            name=name,
            start_time=time.time(),
        )

    def start_span(self, name: str, parent: Span | None = None) -> Span:
        """Create a child span. If *parent* is None the span links to the
        current trace but has no parent (top-level within that trace)."""
        if parent is not None:
            trace_id = parent.trace_id
            parent_id = parent.span_id
        else:
            trace_id = self._current_trace_id
            parent_id = ""
        return Span(
            span_id=uuid.uuid4().hex[:12],
            trace_id=trace_id,
            parent_id=parent_id,
            name=name,
            start_time=time.time(),
        )

    # -- finalisation ----------------------------------------------------------

    def finish_span(self, span: Span) -> None:
        """Finish *span* (if not already finished) and append to the JSONL log."""
        if span.end_time == 0.0:
            span.finish()
        record = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_id": span.parent_id,
            "name": span.name,
            "duration_ms": span.duration_ms(),
            "status": span.status,
            "attributes": span.attributes,
            "events": span.events,
        }
        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- query helpers ---------------------------------------------------------

    def current_trace_id(self) -> str:
        """Return the most recently created trace_id."""
        return self._current_trace_id

    def get_trace_summary(self, trace_id: str) -> dict[str, Any]:
        """Load all spans for *trace_id* from the JSONL log and return a summary."""
        spans: list[dict[str, Any]] = []
        if not self._log_file.exists():
            return {"trace_id": trace_id, "spans": [], "total_duration_ms": 0.0}
        with open(self._log_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("trace_id") == trace_id:
                    spans.append(record)
        root_durations = [s["duration_ms"] for s in spans if s.get("parent_id") == ""]
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": max(root_durations) if root_durations else 0.0,
            "status": "error" if any(s.get("status") == "error" for s in spans) else "ok",
            "spans": spans,
        }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class Metrics:
    """In-memory counters and timing buckets."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._timings: dict[str, list[float]] = {}

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a counter by *value*."""
        self._counters[name] = self._counters.get(name, 0) + value

    def timing(self, name: str, duration_ms: float) -> None:
        """Record a timing observation in milliseconds."""
        self._timings.setdefault(name, []).append(duration_ms)

    def get(self, name: str) -> float:
        """Return the current value of counter *name* (0 if unknown)."""
        return self._counters.get(name, 0)

    def summary(self) -> dict[str, Any]:
        """Return all metrics as a plain dict."""
        timing_summary: dict[str, Any] = {}
        for name, values in self._timings.items():
            timing_summary[name] = {
                "count": len(values),
                "total_ms": sum(values),
                "avg_ms": sum(values) / len(values) if values else 0,
                "min_ms": min(values) if values else 0,
                "max_ms": max(values) if values else 0,
            }
        return {
            "counters": dict(self._counters),
            "timings": timing_summary,
        }


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

tracer = Tracer()
metrics = Metrics()


# ---------------------------------------------------------------------------
# TraceContext context manager
# ---------------------------------------------------------------------------

@contextmanager
def TraceContext(name: str, **attributes: Any):
    """Convenience context manager for instrumenting a block of code.

    Usage::

        with TraceContext("tool_call", tool_name="read_file") as span:
            result = do_something()
            span.set_attribute("result_length", len(result))
    """
    parent = _current_span.get()
    span = tracer.start_span(name, parent=parent) if parent is not None else tracer.start_trace(name)
    for key, value in attributes.items():
        span.set_attribute(key, value)

    token = _current_span.set(span)
    try:
        yield span
    except (OSError, ValueError, RuntimeError):
        span.finish(status="error")
        span.add_event("exception")
        tracer.finish_span(span)
        raise
    else:
        if span.end_time == 0.0:
            span.finish(status="ok")
        tracer.finish_span(span)
    finally:
        _current_span.reset(token)


_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "_current_span", default=None
)


# ---------------------------------------------------------------------------
# Helper: recent traces
# ---------------------------------------------------------------------------

def get_recent_traces(limit: int = 20) -> list[dict[str, Any]]:
    """Read the last *limit* trace records from the JSONL log."""
    log_file = tracer._log_file
    if not log_file.exists():
        return []
    with open(log_file, encoding="utf-8") as fh:
        lines = fh.readlines()
    results: list[dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(results) >= limit:
            break
    return results
