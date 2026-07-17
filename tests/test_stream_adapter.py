"""Regression test for stream_adapter race condition fix."""

from __future__ import annotations


class TestStreamAdapterRace:
    """Verify stream_adapter handles fast generators (race condition fix)."""

    def test_fast_generator_doesnt_lose_items(self):
        """Fast in-memory generator should deliver all deltas (was 0)."""
        from core.stream_adapter import consume_stream

        deltas = [{"content": "a"}, {"content": "b"}, {"_usage": {"total": 2}}]
        results = list(consume_stream(lambda: iter(deltas)))
        assert len(results) >= 2, f"Lost items: got {len(results)}, expected >=2"
        assert any(d.get("content") == "a" for d in results)
        assert any(d.get("content") == "b" for d in results)

    def test_single_item_fast_generator(self):
        """Single-item generator should work."""
        from core.stream_adapter import consume_stream

        results = list(consume_stream(lambda: iter([{"content": "x"}])))
        assert len(results) >= 1
        assert results[0].get("content") == "x"

    def test_delta_processor_integration(self):
        """DeltaProcessor + consume_stream together should produce text."""
        from core.stream_adapter import DeltaProcessor, consume_stream

        dp = DeltaProcessor("deepseek-v4-flash")
        events = []
        for delta in consume_stream(lambda: iter([{"content": "hi"}])):
            for k, p in dp.process_delta(delta):
                events.append((k, p))
        buf, tc, err, usage = dp.finalize()
        assert len(events) >= 1, "No events from DeltaProcessor"
        assert any(k == "text" for k, _ in events)
        assert buf == "hi"
