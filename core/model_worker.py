from __future__ import annotations

import contextlib
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Mapping, Protocol


class RuntimeEventType(str, Enum):
    CHUNK = "CHUNK"
    ERROR = "ERROR"
    DONE = "DONE"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    type: RuntimeEventType
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @property
    def terminal(self) -> bool:
        return self.type is RuntimeEventType.DONE


class ClosableStream(Protocol):
    def __iter__(self) -> Iterator[Any]:
        ...

    def close(self) -> None:
        ...


class ModelStreamError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        cancelled: bool = False,
        elapsed_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.cancelled = cancelled
        self.elapsed_seconds = elapsed_seconds

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "cancelled": self.cancelled,
            "terminal": True,
        }
        if self.elapsed_seconds is not None:
            payload["elapsed_seconds"] = round(self.elapsed_seconds, 3)
        return payload


StreamFactory = Callable[[], Any]


class ModelWorker:
    """
    Run model stream creation and socket consumption in a dedicated thread.

    The caller only consumes RuntimeEvent objects from event_queue. The
    watchdog enforces:
      - first meaningful model delta timeout
      - interval timeout between meaningful deltas
      - total request timeout
      - explicit user cancellation

    A meaningful delta is content, reasoning_content, tool_calls,
    function_call, finish_reason, or a non-empty plain string/bytes chunk.
    Role-only and keepalive chunks are forwarded but do not reset deadlines.
    """

    def __init__(
        self,
        stream_factory: StreamFactory,
        *,
        first_token_timeout: float = 30.0,
        stream_idle_timeout: float = 30.0,
        total_timeout: float = 300.0,
        watchdog_interval: float = 0.05,
        name: str = "crux-model",
    ) -> None:
        for field_name, value in (
            ("first_token_timeout", first_token_timeout),
            ("stream_idle_timeout", stream_idle_timeout),
            ("total_timeout", total_timeout),
            ("watchdog_interval", watchdog_interval),
        ):
            if value <= 0:
                raise ValueError(f"{field_name} must be > 0")

        if total_timeout < first_token_timeout:
            raise ValueError(
                "total_timeout cannot be shorter than first_token_timeout"
            )

        self.stream_factory = stream_factory
        self.first_token_timeout = first_token_timeout
        self.stream_idle_timeout = stream_idle_timeout
        self.total_timeout = total_timeout
        self.watchdog_interval = watchdog_interval
        self.name = name

        self.event_queue: queue.Queue[RuntimeEvent] = queue.Queue()
        self.cancel_event = threading.Event()
        self.done_event = threading.Event()

        self._start_lock = threading.Lock()
        self._terminal_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stream_lock = threading.Lock()

        self._reader_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._stream: Any = None
        self._stream_exit: Callable[..., Any] | None = None

        self._started_at = 0.0
        self._first_activity_at: float | None = None
        self._last_activity_at: float | None = None
        self._terminal_sent = False

    @property
    def started(self) -> bool:
        return self._reader_thread is not None

    @property
    def done(self) -> bool:
        return self.done_event.is_set()

    def start(self) -> "ModelWorker":
        with self._start_lock:
            if self._reader_thread is not None:
                return self

            self._started_at = time.monotonic()

            self._reader_thread = threading.Thread(
                target=self._reader_main,
                name=f"{self.name}-reader",
                daemon=True,
            )
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_main,
                name=f"{self.name}-watchdog",
                daemon=True,
            )

            self._watchdog_thread.start()
            self._reader_thread.start()

        return self

    def cancel(self, reason: str = "cancelled by user") -> bool:
        self.cancel_event.set()

        emitted = self._finish_error(
            code="USER_CANCELLED",
            message=reason,
            retryable=False,
            cancelled=True,
        )

        self._close_stream()
        return emitted

    def iter_events(
        self,
        *,
        external_cancel_event: threading.Event | None = None,
        poll_interval: float = 0.1,
    ) -> Iterator[RuntimeEvent]:
        self.start()

        while True:
            if (
                external_cancel_event is not None
                and external_cancel_event.is_set()
                and not self.done
            ):
                self.cancel("external cancellation requested")

            try:
                event = self.event_queue.get(timeout=poll_interval)
            except queue.Empty:
                reader = self._reader_thread

                if reader is not None and not reader.is_alive() and not self.done:
                    self._finish_error(
                        code="MODEL_READER_DIED",
                        message="model reader stopped without a terminal event",
                        retryable=True,
                    )

                continue

            yield event

            if event.type is RuntimeEventType.DONE:
                return

    def iter_chunks(
        self,
        *,
        external_cancel_event: threading.Event | None = None,
    ) -> Iterator[Any]:
        pending_error: ModelStreamError | None = None

        for event in self.iter_events(
            external_cancel_event=external_cancel_event,
        ):
            if event.type is RuntimeEventType.CHUNK:
                yield event.payload["chunk"]
                continue

            if event.type is RuntimeEventType.ERROR:
                pending_error = ModelStreamError(
                    code=str(
                        event.payload.get(
                            "code",
                            "MODEL_STREAM_ERROR",
                        )
                    ),
                    message=str(
                        event.payload.get(
                            "message",
                            "model stream failed",
                        )
                    ),
                    retryable=bool(
                        event.payload.get(
                            "retryable",
                            False,
                        )
                    ),
                    cancelled=bool(
                        event.payload.get(
                            "cancelled",
                            False,
                        )
                    ),
                    elapsed_seconds=self._optional_float(
                        event.payload.get("elapsed_seconds")
                    ),
                )
                continue

            if event.type is RuntimeEventType.DONE:
                if pending_error is not None:
                    raise pending_error
                return

    def wait_closed(self, timeout: float | None = None) -> bool:
        deadline = (
            None
            if timeout is None
            else time.monotonic() + timeout
        )

        for thread in (
            self._reader_thread,
            self._watchdog_thread,
        ):
            if thread is None or thread is threading.current_thread():
                continue

            remaining = (
                None
                if deadline is None
                else max(
                    0.0,
                    deadline - time.monotonic(),
                )
            )

            thread.join(remaining)

        return not any(
            thread is not None and thread.is_alive()
            for thread in (
                self._reader_thread,
                self._watchdog_thread,
            )
        )

    def _reader_main(self) -> None:
        try:
            raw_stream = self.stream_factory()
            stream = self._enter_stream(raw_stream)
            self._set_stream(stream)

            for chunk in stream:
                if self.cancel_event.is_set() or self.done:
                    return

                if self._is_meaningful_chunk(chunk):
                    self._mark_activity()

                self._emit(
                    RuntimeEvent(
                        RuntimeEventType.CHUNK,
                        {"chunk": chunk},
                    )
                )

            if not self.done:
                self._finish_success("eof")

        except BaseException as exc:
            if self.done:
                return

            if self.cancel_event.is_set():
                self._finish_error(
                    code="USER_CANCELLED",
                    message="model stream cancelled",
                    retryable=False,
                    cancelled=True,
                )
                return

            self._finish_error(
                code="MODEL_STREAM_EXCEPTION",
                message=f"{type(exc).__name__}: {exc}",
                retryable=self._is_retryable_exception(exc),
            )

        finally:
            self._close_stream()

            if not self.done:
                self._finish_error(
                    code="MODEL_STREAM_NO_TERMINAL",
                    message="reader exited without a terminal event",
                    retryable=True,
                )

    def _watchdog_main(self) -> None:
        while not self.done_event.wait(self.watchdog_interval):
            now = time.monotonic()
            elapsed_total = now - self._started_at

            if elapsed_total >= self.total_timeout:
                self.cancel_event.set()

                self._finish_error(
                    code="TOTAL_TIMEOUT",
                    message=(
                        "model stream exceeded total timeout "
                        f"({self.total_timeout:.1f}s)"
                    ),
                    retryable=True,
                    elapsed_seconds=elapsed_total,
                )

                self._close_stream()
                return

            with self._state_lock:
                first_activity_at = self._first_activity_at
                last_activity_at = self._last_activity_at

            if first_activity_at is None:
                if elapsed_total >= self.first_token_timeout:
                    self.cancel_event.set()

                    self._finish_error(
                        code="FIRST_TOKEN_TIMEOUT",
                        message=(
                            "model produced no content, reasoning, or "
                            "tool-call delta within "
                            f"{self.first_token_timeout:.1f}s"
                        ),
                        retryable=True,
                        elapsed_seconds=elapsed_total,
                    )

                    self._close_stream()
                    return

                continue

            assert last_activity_at is not None

            idle_elapsed = now - last_activity_at

            if idle_elapsed >= self.stream_idle_timeout:
                self.cancel_event.set()

                self._finish_error(
                    code="STREAM_IDLE_TIMEOUT",
                    message=(
                        "model produced no content, reasoning, or "
                        "tool-call delta for "
                        f"{self.stream_idle_timeout:.1f}s"
                    ),
                    retryable=True,
                    elapsed_seconds=idle_elapsed,
                )

                self._close_stream()
                return

    def _mark_activity(self) -> None:
        now = time.monotonic()

        with self._state_lock:
            if self._first_activity_at is None:
                self._first_activity_at = now

            self._last_activity_at = now

    def _emit(self, event: RuntimeEvent) -> bool:
        with self._terminal_lock:
            if self._terminal_sent:
                return False

            self.event_queue.put(event)
            return True

    def _finish_success(self, reason: str) -> bool:
        with self._terminal_lock:
            if self._terminal_sent:
                return False

            self._terminal_sent = True
            self.done_event.set()

            self.event_queue.put(
                RuntimeEvent(
                    RuntimeEventType.DONE,
                    {
                        "status": "completed",
                        "reason": reason,
                        "elapsed_seconds": round(
                            time.monotonic() - self._started_at,
                            3,
                        ),
                    },
                )
            )

            return True

    def _finish_error(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        cancelled: bool = False,
        elapsed_seconds: float | None = None,
    ) -> bool:
        with self._terminal_lock:
            if self._terminal_sent:
                return False

            if elapsed_seconds is None:
                elapsed_seconds = max(
                    0.0,
                    time.monotonic() - self._started_at,
                )

            self._terminal_sent = True
            self.done_event.set()

            self.event_queue.put(
                RuntimeEvent(
                    RuntimeEventType.ERROR,
                    {
                        "code": code,
                        "message": message,
                        "retryable": retryable,
                        "cancelled": cancelled,
                        "terminal": True,
                        "elapsed_seconds": round(
                            elapsed_seconds,
                            3,
                        ),
                    },
                )
            )

            self.event_queue.put(
                RuntimeEvent(
                    RuntimeEventType.DONE,
                    {
                        "status": (
                            "cancelled"
                            if cancelled
                            else "error"
                        ),
                        "reason": code,
                        "elapsed_seconds": round(
                            elapsed_seconds,
                            3,
                        ),
                    },
                )
            )

            return True

    def _enter_stream(self, stream: Any) -> Any:
        enter = getattr(stream, "__enter__", None)
        exit_method = getattr(stream, "__exit__", None)

        if callable(enter) and callable(exit_method):
            entered = enter()

            with self._stream_lock:
                self._stream_exit = exit_method

            return entered

        return stream

    def _set_stream(self, stream: Any) -> None:
        with self._stream_lock:
            self._stream = stream

    def _close_stream(self) -> None:
        with self._stream_lock:
            stream = self._stream
            exit_method = self._stream_exit

            self._stream = None
            self._stream_exit = None

        if stream is not None:
            close = getattr(stream, "close", None)

            if callable(close):
                with contextlib.suppress(BaseException):
                    close()

        if exit_method is not None:
            with contextlib.suppress(BaseException):
                exit_method(None, None, None)

    @classmethod
    def _is_meaningful_chunk(cls, chunk: Any) -> bool:
        if isinstance(chunk, str):
            return bool(chunk)

        if isinstance(chunk, (bytes, bytearray)):
            return bool(chunk)

        document = cls._to_mapping(chunk)

        if document is None:
            return True

        error = document.get("error")

        if error:
            return True

        choices = document.get("choices")

        if not isinstance(choices, (list, tuple)):
            for key in (
                "content",
                "text",
                "reasoning_content",
                "tool_calls",
                "function_call",
                "finish_reason",
            ):
                if cls._has_value(document.get(key)):
                    return True

            return False

        for choice in choices:
            choice_map = cls._to_mapping(choice)

            if choice_map is None:
                continue

            delta = cls._to_mapping(
                choice_map.get("delta")
            ) or {}

            for key in (
                "content",
                "reasoning_content",
                "tool_calls",
                "function_call",
            ):
                if cls._has_value(delta.get(key)):
                    return True

            if cls._has_value(choice_map.get("text")):
                return True

            if cls._has_value(
                choice_map.get("finish_reason")
            ):
                return True

        return False

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False

        if isinstance(
            value,
            (str, bytes, bytearray),
        ):
            return bool(value)

        if isinstance(
            value,
            (list, tuple, dict, set),
        ):
            return bool(value)

        return True

    @staticmethod
    def _to_mapping(
        value: Any,
    ) -> Mapping[str, Any] | None:
        if isinstance(value, Mapping):
            return value

        model_dump = getattr(
            value,
            "model_dump",
            None,
        )

        if callable(model_dump):
            with contextlib.suppress(BaseException):
                dumped = model_dump()

                if isinstance(dumped, Mapping):
                    return dumped

        to_dict = getattr(
            value,
            "to_dict",
            None,
        )

        if callable(to_dict):
            with contextlib.suppress(BaseException):
                dumped = to_dict()

                if isinstance(dumped, Mapping):
                    return dumped

        value_dict = getattr(
            value,
            "__dict__",
            None,
        )

        if isinstance(value_dict, Mapping):
            return value_dict

        return None

    @staticmethod
    def _is_retryable_exception(
        exc: BaseException,
    ) -> bool:
        name = type(exc).__name__.lower()
        message = str(exc).lower()

        retryable_tokens = (
            "timeout",
            "connection",
            "transport",
            "temporarily",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
        )

        return any(
            token in name or token in message
            for token in retryable_tokens
        )

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> float | None:
        try:
            return (
                None
                if value is None
                else float(value)
            )
        except (TypeError, ValueError):
            return None


class ThreadedModelStream:
    """
    Iterable façade compatible with existing
    `_consume_stream_delta(stream)`.

    The original provider `create(..., stream=True)` call and subsequent
    socket reads both execute in ModelWorker's reader thread.
    """

    def __init__(
        self,
        stream_factory: StreamFactory,
        *,
        owner: Any = None,
        cancel_event: threading.Event | None = None,
        first_token_timeout: float = 30.0,
        stream_idle_timeout: float = 30.0,
        total_timeout: float = 300.0,
        name: str = "crux-model",
    ) -> None:
        self.worker = ModelWorker(
            stream_factory,
            first_token_timeout=first_token_timeout,
            stream_idle_timeout=stream_idle_timeout,
            total_timeout=total_timeout,
            name=name,
        )

        self.owner = owner
        self.cancel_event = cancel_event
        self._iterator: Iterator[Any] | None = None
        self._closed = False

        if owner is not None:
            setattr(
                owner,
                "_active_model_stream",
                self,
            )

    def __iter__(self) -> "ThreadedModelStream":
        return self

    def __next__(self) -> Any:
        if self._closed:
            raise StopIteration

        if self._iterator is None:
            self._iterator = self.worker.iter_chunks(
                external_cancel_event=self.cancel_event,
            )

        try:
            return next(self._iterator)
        except StopIteration:
            self._clear_owner()
            raise
        except BaseException:
            self._clear_owner()
            raise

    def __enter__(self) -> "ThreadedModelStream":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc: Any,
        tb: Any,
    ) -> None:
        self.close()

    def cancel(
        self,
        reason: str = "cancelled by user",
    ) -> bool:
        return self.worker.cancel(reason)

    def close(
        self,
        reason: str = "model stream closed",
    ) -> None:
        if self._closed:
            return

        self._closed = True

        if not self.worker.done:
            self.worker.cancel(reason)

        self.worker.wait_closed(timeout=0.5)
        self._clear_owner()

    def _clear_owner(self) -> None:
        owner = self.owner

        if (
            owner is not None
            and getattr(
                owner,
                "_active_model_stream",
                None,
            )
            is self
        ):
            setattr(
                owner,
                "_active_model_stream",
                None,
            )


__all__ = [
    "ModelStreamError",
    "ModelWorker",
    "RuntimeEvent",
    "RuntimeEventType",
    "ThreadedModelStream",
]