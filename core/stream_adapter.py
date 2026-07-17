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
from typing import Any, Callable, Iterator

logger = logging.getLogger("crux.stream_adapter")

DEFAULT_FIRST_TOKEN_TIMEOUT = 30.0
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
                    if hasattr(stream, 'close'):
                        stream.close()
                except Exception:
                    pass
        except Exception as exc:
            _error[0] = exc
        finally:
            _reader_done.set()

    _thread = threading.Thread(target=_reader, daemon=True, name="crux-stream")
    _thread.start()

    _last_data = time.monotonic()
    while not _reader_done.is_set():
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
