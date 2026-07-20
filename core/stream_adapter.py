"""StreamAdapter — the ONLY place that calls client.chat_stream() and converts
provider deltas into (kind, payload) tuples.

Per GPT v6.2: '只有一个地方负责 provider delta → RuntimeEvent'

All ChatSession stream consumption routes through this module.
ChatSession no longer directly understands HTTP streams or raw provider deltas.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

logger = logging.getLogger("crux.stream_adapter")

DEFAULT_FIRST_TOKEN_TIMEOUT = 30.0  # TODO: wire into consume_stream() first-token watchdog
DEFAULT_STREAM_IDLE_TIMEOUT = 30.0


def consume_stream(
    stream_factory: Callable[[], Iterator[dict]],
    *,
    idle_timeout: float = DEFAULT_STREAM_IDLE_TIMEOUT,
) -> Iterator[tuple[str, Any]]:
    """Consume a provider stream with timeout guard.

    Runs the stream in a daemon thread (ModelWorker pattern).
    Main thread reads from queue with idle_timeout watchdog.
    Yields (kind, payload) tuples for backward compatibility.

    Args:
        stream_factory: Callable that returns a delta iterator
        idle_timeout: Seconds of silence before watchdog kills stream

    Yields:
        (kind, payload) tuples — same protocol as _consume_stream_delta
    """
    _delta_q: queue.Queue = queue.Queue()
    _reader_done = threading.Event()
    _cancel = threading.Event()
    _error: list[Exception | None] = [None]

    def _reader():
        try:
            stream = stream_factory()
            while not _cancel.is_set():
                try:
                    _item = next(stream)
                    _delta_q.put(_item)
                except StopIteration:
                    break
            if _cancel.is_set():
                try:
                    if hasattr(stream, "close"):
                        stream.close()
                except Exception:
                    logging.getLogger(__name__).debug("silent except", exc_info=True)
        except Exception as exc:
            _error[0] = exc
        finally:
            _reader_done.set()

    _thread = threading.Thread(target=_reader, daemon=True, name="crux-stream")
    _thread.start()

    _last_data = time.monotonic()
    while not _reader_done.is_set() or not _delta_q.empty():
        try:
            _item = _delta_q.get(timeout=2.0)
            _last_data = time.monotonic()
            yield _item
        except queue.Empty:
            if time.monotonic() - _last_data > idle_timeout:
                _cancel.set()
                _error[0] = RuntimeError(f"Stream timeout: no data for {idle_timeout:.0f}s")
                break

    _thread.join(timeout=5)
    if _thread.is_alive():
        logger.warning("Stream reader thread did not exit in 5s — abandoned as daemon")
    if _error[0]:
        raise _error[0]


class DeltaProcessor:
    """Pure converter: provider delta dicts → (kind, payload) tuples.

    Extracted from ChatSession._consume_stream_delta per GPT v6.2 plan.
    This class has NO stream I/O — it only processes individual delta dicts.
    ChatSession calls process_delta() for each delta from stream_adapter.
    """

    def __init__(self, model: str):
        self.model = model
        self.buffer = ""
        self.tool_calls: list[dict] = []
        self.stream_error = False
        self.last_usage: dict | None = None
        self._first_token_at: float | None = None
        self._stream_start: float | None = None

    def process_delta(self, delta: dict):
        """Process one provider delta. Yields (kind, payload) tuples."""
        import time as _time

        if self._stream_start is None:
            self._stream_start = _time.monotonic()

        # Provider-aware thinking field extraction
        from core.provider_adapter import get_adapter, get_capability

        cap = get_capability(self.model)
        adapter = get_adapter(cap.provider_id if cap else "deepseek")
        think_field = adapter.thinking_response_field
        if delta.get(think_field):
            yield ("thinking", delta[think_field])

        if delta.get("content"):
            chunk = delta["content"]
            if self._first_token_at is None:
                self._first_token_at = _time.monotonic()
                elapsed = self._first_token_at - (self._stream_start or 0)
                if elapsed > 15.0:
                    yield ("info", f"首 token 延迟 {elapsed:.1f}s")
            self.buffer += chunk
            if not delta.get("_error"):
                yield ("text", chunk)

        if delta.get("tool_calls"):
            self.tool_calls.extend(delta["tool_calls"])
        if delta.get("_finish") == "error":
            self.stream_error = True
        if "_usage" in delta:
            self.last_usage = delta["_usage"]

    def finalize(self):
        """Post-processing after all deltas consumed. Returns (buffer, tool_calls, error, usage)."""
        if not self.tool_calls and self.buffer:
            try:
                from core.tool_call_parser import extract_tool_calls

                xml_tools, _ = extract_tool_calls(self.buffer)
                if xml_tools:
                    self.tool_calls.extend(xml_tools)
                    logger.debug("parsed %d XML tool calls from buffer", len(xml_tools))
            except ImportError:
                pass
        return (self.buffer, self.tool_calls, self.stream_error, self.last_usage)
