"""Tests for ui/status_bar.py — rendering, truncation, edge cases."""

from ui.status_bar import StatusBar


def _make_bar(model="CRUX"):
    return StatusBar(model_fn=lambda: model, cwd="~/test", model=model)


class TestStatusBarBasics:
    def test_render_returns_formatted_text(self):
        assert _make_bar().render() is not None

    def test_model_in_output(self):
        r = StatusBar(model_fn=None, cwd="~/test", model="deepseek-v4-pro").render()
        text = " ".join(t[1] for t in r if isinstance(t, tuple) and len(t) > 1)
        assert "deepseek" in text.lower() or "v4" in text.lower()

    def test_set_thinking(self):
        sb = _make_bar()
        sb.set_thinking(True)
        assert sb._thinking is True

    def test_set_hint(self):
        sb = _make_bar()
        sb.set_hint("test hint")
        assert sb._hint == "test hint"

    def test_set_latency_no_crash(self):
        _make_bar().set_latency(1.5)

    def test_set_model(self):
        # model_fn callable takes priority; pass model directly
        sb = StatusBar(model_fn=None, cwd="~/test", model="flash-model")
        r = sb.render()
        text = " ".join(t[1] for t in r if isinstance(t, tuple) and len(t) > 1)
        assert "flash" in text.lower()


class TestEdgeCases:
    def test_empty_model(self):
        assert _make_bar("").render() is not None

    def test_long_model(self):
        assert _make_bar("a" * 100).render() is not None

    def test_unicode_model(self):
        assert _make_bar("测试模型").render() is not None

    def test_concurrent_sets(self):
        sb = _make_bar()
        for i in range(50):
            sb.set_model(f"model-{i}")
            sb.set_thinking(i % 2 == 0)
        assert sb.render() is not None

    def test_render_never_raises(self):
        sb = _make_bar()
        for _ in range(10):
            sb.render()

    def test_no_watchdog_alert_when_clean(self):
        assert "⚠" not in str(_make_bar().render())
