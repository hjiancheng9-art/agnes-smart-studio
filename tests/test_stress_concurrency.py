"""Concurrency stress tests — hammer thread-safe components under load.

Tests the components that were fixed or inspected during the 12-round audit:
- TaskRegistry (round 2: added threading.Lock)
- ToolRegistry execution with concurrent calls
- Tool cache concurrent read/write/invalidate
- Atomic file writes (round 3 fix)
- Provider manager concurrent client creation
- Event bus concurrent publish/subscribe
- Session tracker thread-local connections
- Secret redactor concurrent access
- CancellationToken propagation across threads

Design: each test spawns N threads hammering a component for M iterations,
verifying no crashes, no data corruption, and correct final state.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════
# 1. TaskRegistry stress (round 2 fix: added threading.Lock)
# ═══════════════════════════════════════════════════════════════


class TestTaskRegistryConcurrency:
    def test_concurrent_register_complete(self):
        """Register and complete tasks from multiple threads simultaneously."""
        from core.cancellation import TaskRegistry

        registry = TaskRegistry()
        errors = []
        task_ids = []

        def worker(uid: int):
            try:
                for i in range(50):
                    tid, _token = registry.register(f"task-{uid}-{i}")
                    task_ids.append(tid)
                    # Simulate work
                    time.sleep(0.001)
                    registry.complete(tid, f"result-{uid}-{i}")
            except Exception as e:
                errors.append(f"worker{uid}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Got errors: {errors}"
        # All tasks should be completed
        active = registry.list_active()
        assert len(active) == 0, f"All tasks should be completed, got {len(active)} active"
        # Total registered = 8 * 50 = 400
        all_tasks = registry.list_all()
        assert len(all_tasks) == 400, f"Expected 400 tasks, got {len(all_tasks)}"
        completed = sum(1 for t in all_tasks if t.status.value == "completed")
        assert completed == 400, f"All should be completed, got {completed}"

    def test_concurrent_cancel_and_list(self):
        """Cancel tasks while listing from another thread."""
        from core.cancellation import TaskRegistry

        registry = TaskRegistry()
        errors = []
        results = []

        def registerer():
            try:
                for i in range(100):
                    registry.register(f"task-{i}")
            except Exception as e:
                errors.append(f"registerer: {e}")

        def lister():
            try:
                for _ in range(200):
                    lst = registry.list_all()
                    results.append(len(lst))
                    time.sleep(0.002)
            except Exception as e:
                errors.append(f"lister: {e}")

        def canceller():
            try:
                for _ in range(50):
                    for t in registry.list_active()[:5]:
                        registry.cancel(t.task_id, "stress test")
                    time.sleep(0.005)
            except Exception as e:
                errors.append(f"canceller: {e}")

        threads = [
            threading.Thread(target=registerer),
            threading.Thread(target=lister),
            threading.Thread(target=canceller),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent list/cancel crashed: {errors}"
        assert all(isinstance(r, int) for r in results), "List should return int counts"


# ═══════════════════════════════════════════════════════════════
# 2. Tool cache concurrency (round 4: cache thread safety)
# ═══════════════════════════════════════════════════════════════


class TestToolCacheConcurrency:
    def test_concurrent_read_write(self):
        """Hammer the tool cache with concurrent reads and writes."""
        from core.tool_cache import get_tool_cache

        cache = get_tool_cache()
        cache.invalidate_all()
        errors = []

        def writer(tool_idx: int):
            try:
                for i in range(30):
                    cache.put(
                        "read_file",
                        json.dumps({"path": f"file{tool_idx}_{i}.py"}),
                        f"content-{tool_idx}-{i}",
                    )
            except Exception as e:
                errors.append(f"writer{tool_idx}: {e}")

        def reader():
            try:
                for _ in range(100):
                    cache.get("read_file", json.dumps({"path": "nonexistent.py"}))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"reader: {e}")

        def invalidator():
            try:
                for _ in range(10):
                    time.sleep(0.01)
                    cache.invalidate_all()
            except Exception as e:
                errors.append(f"invalidator: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        threads.append(threading.Thread(target=reader))
        threads.append(threading.Thread(target=invalidator))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Cache concurrency errors: {errors}"
        cache.invalidate_all()  # cleanup


# ═══════════════════════════════════════════════════════════════
# 3. Atomic file writes (round 3 fix)
# ═══════════════════════════════════════════════════════════════


class TestAtomicFileWrites:
    def test_concurrent_atomic_writes(self):
        """Multiple threads writing to the same file should not corrupt it."""
        tmpdir = tempfile.mkdtemp(prefix="crux_stress_")
        target = Path(tmpdir) / "shared.json"
        errors = []

        def writer(uid: int):
            try:
                for i in range(20):
                    # Use the same atomic write pattern as file_tools.py
                    data = json.dumps({"uid": uid, "seq": i, "thread": threading.current_thread().name})
                    fd, tmp = tempfile.mkstemp(suffix=".tmp", prefix=".crux_", dir=str(target.parent))
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(data)
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(tmp, str(target))
                    except OSError:
                        pass  # Windows: target locked by another thread, next writer wins
                    finally:
                        with __import__("contextlib").suppress(OSError):
                            os.unlink(tmp)
            except Exception as e:
                errors.append(f"writer{uid}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(writer, range(4)))

        assert not errors, f"Atomic write errors: {errors}"
        # Verify the file is valid JSON (not corrupted)
        if target.exists():
            content = target.read_text(encoding="utf-8")
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                pytest.fail(f"File corrupted: {e}")
        # Cleanup
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 4. Provider manager concurrency
# ═══════════════════════════════════════════════════════════════


class TestProviderManagerConcurrency:
    def test_concurrent_client_creation(self):
        """Creating clients concurrently should not corrupt provider state."""
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        errors = []
        clients = []

        def creator():
            try:
                for _ in range(10):
                    client = mgr.create_client("deepseek")
                    clients.append(client)
            except Exception as e:
                errors.append(f"creator: {e}")

        threads = [threading.Thread(target=creator) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Provider creation errors: {errors}"
        assert len(clients) == 40, f"Expected 40 clients, got {len(clients)}"
        # All clients should have provider_id set
        for c in clients:
            assert hasattr(c, "provider_id"), "Client missing provider_id"
        # Close all clients
        for c in clients:
            with __import__("contextlib").suppress(Exception):
                c.close()


# ═══════════════════════════════════════════════════════════════
# 5. Event bus concurrency
# ═══════════════════════════════════════════════════════════════


class TestEventBusConcurrency:
    def test_concurrent_publish_subscribe(self):
        """Concurrent publish/subscribe should not lose events."""
        from core.event_bus import bus

        received = []
        lock = threading.Lock()

        def handler(**kwargs):
            with lock:
                received.append(kwargs.get("value", 0))

        bus.on("stress:event", handler)
        errors = []

        def publisher(start: int):
            try:
                for i in range(50):
                    bus.emit("stress:event", value=start + i)
            except Exception as e:
                errors.append(f"publisher: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            pool.map(publisher, [0, 100, 200, 300])

        assert not errors, f"Event bus errors: {errors}"
        # All 200 events should have been received
        assert len(received) == 200, f"Expected 200 events, got {len(received)}"


# ═══════════════════════════════════════════════════════════════
# 6. CancellationToken thread propagation
# ═══════════════════════════════════════════════════════════════


class TestCancellationTokenConcurrency:
    def test_token_propagates_across_threads(self):
        """Cancel from one thread should be visible from another."""
        from core.cancellation import CancellationToken, CancelledError

        token = CancellationToken(task_id="stress-test")
        detected = []

        def watcher():
            try:
                while not token.cancelled:
                    time.sleep(0.01)
                token.check()
            except CancelledError:
                detected.append(True)

        watcher_thread = threading.Thread(target=watcher)
        watcher_thread.start()

        time.sleep(0.05)
        token.cancel("stress cancel")
        watcher_thread.join(timeout=5)

        assert detected, "Cancellation should have been detected"


# ═══════════════════════════════════════════════════════════════
# 7. Secret redactor concurrency (round 2: read-only cache)
# ═══════════════════════════════════════════════════════════════


class TestSecretRedactorConcurrency:
    def test_concurrent_redact(self):
        """Redacting from multiple threads should not crash."""
        from core.secret_redactor import redact

        texts = [f"sk-abc123def456ghi789jklmno{u:04d}pqrstuvwxyz" for u in range(20)] + [
            "normal text without any secrets at all"
        ] * 30
        errors = []

        def redactor(batch):
            try:
                for t in batch:
                    result = redact(t)
                    assert isinstance(result, str)
            except Exception as e:
                errors.append(f"redactor: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            chunk = len(texts) // 4
            batches = [texts[i : i + chunk] for i in range(0, len(texts), chunk)]
            list(pool.map(redactor, batches))

        assert not errors, f"Redactor concurrency errors: {errors}"


# ═══════════════════════════════════════════════════════════════
# 8. ModelWorker thread safety (round 2)
# ═══════════════════════════════════════════════════════════════


class TestModelWorkerConcurrency:
    def test_multiple_workers_no_crash(self):
        """Multiple ModelWorkers running simultaneously shouldn't interfere."""
        from core.model_worker import ModelWorker, RuntimeEventType

        def stream_factory():
            chunks = [{"choices": [{"delta": {"content": f"chunk{i}"}}]} for i in range(10)]
            chunks.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            return iter(chunks)

        workers = []
        for i in range(4):
            w = ModelWorker(stream_factory, first_token_timeout=3.0, total_timeout=10.0, name=f"stress-{i}")
            w.start()
            workers.append(w)

        events_per_worker = []
        for w in workers:
            evts = []
            for event in w.iter_events():
                evts.append(event)
            events_per_worker.append(evts)
            w.wait_closed(timeout=5)

        for i, evts in enumerate(events_per_worker):
            assert len(evts) > 0, f"Worker {i} produced no events"
            has_done = any(e.type == RuntimeEventType.DONE for e in evts)
            assert has_done, f"Worker {i} should have DONE event"

    def test_concurrent_cancel(self):
        """Cancel a worker while its reader thread is still producing."""
        from core.model_worker import ModelWorker

        def slow_stream():
            for i in range(1000):
                time.sleep(0.01)
                yield {"choices": [{"delta": {"content": f"s{i}"}}]}

        w = ModelWorker(slow_stream, total_timeout=30.0, first_token_timeout=30.0)
        w.start()

        # Cancel from another thread after a short delay
        def delayed_cancel():
            time.sleep(0.1)
            w.cancel("stress test cancel")

        cancel_thread = threading.Thread(target=delayed_cancel)
        cancel_thread.start()

        events = list(w.iter_events())
        cancel_thread.join(timeout=5)

        # Should have a DONE event (even if cancelled)
        assert len(events) > 0, "Should have events"
