"""Contract tests for ui.render.StreamingRenderer — the single-commit DNA.

These tests guard the "输出不重复" (no duplicate output) invariant directly
on the StreamingRenderer class, independent of ChatSession or send_stream.

Invariant 1: Live is always transient — stop() never fixates text.
Invariant 2: commit() prints only the un-flushed tail — each character printed exactly once.
Invariant 3: Side-effects are commit boundaries — text before the effect is fixated first.
Invariant 4: Empty streams produce no output.
Invariant 5: Double-commit is idempotent (no duplicate output).
"""
# pyright: reportAttributeAccessIssue=false

import io
import sys
from pathlib import Path

import pytest
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.render import StreamingRenderer


def _make_renderer(console=None) -> tuple[StreamingRenderer, io.StringIO]:
    """Create a StreamingRenderer with a capturing console."""
    captured = io.StringIO()
    c = console or Console(file=captured, force_terminal=False, color_system=None, width=120)
    r = StreamingRenderer(c)
    return r, captured


class TestStreamingRendererBasic:
    """Invariant 2: commit() 只打印未落盘的尾部，每个字符恰好一次。"""

    def test_single_chunk_committed_once(self):
        r, cap = _make_renderer()
        r.start()
        r.append_text("Hello")
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("Hello") == 1

    def test_multiple_chunks_no_prefix_duplication(self):
        """复刻旧 bug：前缀不应被重复打印。

        旧 _stream_chat 的 bug 形态：live.update 在 chunk 4 固化快照，
        然后 console.print(Markdown(buf)) 又打完整 buf → 前缀出现两次。
        StreamingRenderer 的 transient+commit 模型消除了这问题。
        """
        r, cap = _make_renderer()
        chunks = ["你好", "，", "世界", "！", "答案"]
        r.start()
        for c in chunks:
            r.append_text(c)
        r.stop()
        r.commit()
        out = cap.getvalue()
        # 前 4 个 chunk = "你好，世界！"，旧 bug 下出现 2 次
        assert out.count("你好，世界！") == 1, f"前缀重复！\n{out}"
        assert out.count("答案") == 1, f"尾部重复！\n{out}"

    def test_every_unique_chunk_appears_once(self):
        """每个独立 chunk 在屏幕上恰好出现一次。"""
        r, cap = _make_renderer()
        chunks = [f"块{i}" for i in range(9)]  # 9 chunks > RENDER_EVERY_N(4)
        r.start()
        for c in chunks:
            r.append_text(c)
        r.stop()
        r.commit()
        out = cap.getvalue()
        for c in chunks:
            assert out.count(c) == 1, f"{c!r} 出现了 {out.count(c)} 次\n{out}"

    def test_commit_on_exact_boundary(self):
        """chunk 数 = RENDER_EVERY_N 的倍数时也不重复。"""
        r, cap = _make_renderer()
        chunks = [f"X{i}" for i in range(8)]  # 8 % 4 == 0
        r.start()
        for c in chunks:
            r.append_text(c)
        r.stop()
        r.commit()
        out = cap.getvalue()
        for c in chunks:
            assert out.count(c) == 1

    def test_long_text_no_truncation(self):
        """200+ 字符的长文本完整输出，无截断。"""
        r, cap = _make_renderer()
        text = "这是很长的一段测试文本。" * 30  # ~450 chars
        r.start()
        for i in range(0, len(text), 10):
            r.append_text(text[i : i + 10])
        r.stop()
        r.commit()
        out = cap.getvalue()
        # 全量文本应完整出现在输出中（去空白后比对）
        cleaned = out.replace("\n", "").replace(" ", "")
        assert text in cleaned, f"长文本被截断！期望 {len(text)} 字符"
        # 总输出长度不应远大于原始文本（不允许重复输出）
        # 允许一定 margin（Markdown 渲染可能加空白），但不应超过 2x
        assert len(cleaned) < len(text) * 1.5

    def test_empty_chunks_ignored(self):
        """空字符串 chunk 不产生输出。"""
        r, cap = _make_renderer()
        r.start()
        r.append_text("")
        r.append_text("")
        r.stop()
        r.commit()
        assert cap.getvalue() == ""


class TestStreamingRendererSideEffects:
    """Invariant 3: 副作用是落盘边界，前后文本分段落盘。"""

    def test_info_boundary_splits_output(self):
        """info 副作用后，新文本不与旧文本重叠。"""
        effects = []
        r, cap = _make_renderer()
        r._handlers = {"info": lambda k, p: effects.append(p)}
        r.start()
        r.append_text("第一段。")
        r.run_side_effect("info", "提示")
        r.append_text("第二段。")
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("第一段。") == 1
        assert out.count("第二段。") == 1
        assert len(effects) == 1
        assert effects[0] == "提示"

    def test_unknown_side_effect_still_commits(self):
        """未注册的 kind 仍触发落盘边界（commit），不报错。"""
        r, cap = _make_renderer()
        r.start()
        r.append_text("前半。")
        r.run_side_effect("unknown_kind", "whatever")  # no handler
        r.append_text("后半。")
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("前半。") == 1
        assert out.count("后半。") == 1

    def test_multiple_side_effects(self):
        """连续多个副作用边界不累积重复。"""
        effects = []
        r, cap = _make_renderer()
        r._handlers = {"info": lambda k, p: effects.append(p)}
        r.start()
        r.append_text("A")
        r.run_side_effect("info", "1")
        r.append_text("B")
        r.run_side_effect("info", "2")
        r.append_text("C")
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("A") == 1
        assert out.count("B") == 1
        assert out.count("C") == 1
        assert len(effects) == 2


class TestStreamingRendererIdempotent:
    """Invariant 5: 多次 commit 是幂等的。"""

    def test_double_commit_no_duplicate(self):
        r, cap = _make_renderer()
        r.start()
        r.append_text("ABC")
        r.stop()
        r.commit()
        r.commit()  # 第二次应该空操作
        out = cap.getvalue()
        assert out.count("ABC") == 1

    def test_triple_commit_no_duplicate(self):
        r, cap = _make_renderer()
        r.start()
        r.append_text("XYZ")
        r.stop()
        r.commit()
        r.commit()
        r.commit()
        out = cap.getvalue()
        assert out.count("XYZ") == 1


class TestStreamingRendererContextManager:
    """验证 with 语句的 __enter__/__exit__ 正确管理生命周期。"""

    def test_context_manager_auto_commit(self):
        with _make_renderer()[0] as r:
            r.append_text("自动落盘")
        out = r.console.file.getvalue()
        assert "自动落盘" in out

    def test_context_manager_no_duplicate(self):
        r, cap = _make_renderer()
        with r:
            r.append_text("唯一")
        out = cap.getvalue()
        assert out.count("唯一") == 1

    def test_empty_context_no_output(self):
        r, cap = _make_renderer()
        with r:
            pass  # 空流
        assert cap.getvalue() == ""


class TestStreamingRendererProperties:
    """buffer 和 flushed_len 只读视图正确反映状态。"""

    def test_buffer_accumulates(self):
        r, _ = _make_renderer()
        r.start()
        r.append_text("a")
        assert r.buffer == "a"
        r.append_text("b")
        assert r.buffer == "ab"

    def test_flushed_len_advances_on_commit(self):
        r, _ = _make_renderer()
        r.start()
        r.append_text("hello")
        assert r.flushed_len == 0
        r.commit()
        assert r.flushed_len == 5

    def test_flushed_len_does_not_advance_on_empty_commit(self):
        r, _ = _make_renderer()
        r.start()
        r.commit()  # 无文本
        assert r.flushed_len == 0


# ── 仓库级守卫：禁止 ui/render.py 外直接用 rich.live.Live ──────────────
# 这是缺陷 3 的修复：renderer 是流式渲染的唯一合法网关。
# 任何想在 render.py 外用 Live 的人，应把逻辑下沉到 renderer 或用 StreamingRenderer。
# 测试文件内 import Live（用于反证测试）不在此限。

_LIVE_IMPORT_PATTERN = "from rich.live import Live"
_LIVE_GATEWAY_FILE = "ui/render.py"


class TestLiveImportGateway:
    """rich.live.Live 只允许 ui/render.py 导入（强制网关）。"""

    def test_live_import_only_in_renderer(self):
        """扫描仓库 .py 文件，确认只有 ui/render.py import Live。"""
        root = Path(__file__).resolve().parent.parent
        violations: list[str] = []
        for py_file in root.rglob("*.py"):
            # 跳过测试文件（反证测试需要 import Live 来 monkeypatch）
            if "tests" in py_file.parts:
                continue
            # 跳过 __pycache__
            if "__pycache__" in py_file.parts:
                continue
            # 跳过构建产物 / 第三方目录（非一手源码，扫描它们会误报）
            if py_file.parts and py_file.parts[0] in ("build", "dist", ".venv", "venv", "node_modules"):
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(_LIVE_IMPORT_PATTERN) or stripped.startswith("import rich.live"):
                    rel = py_file.relative_to(root)
                    if str(rel).replace("\\", "/") != _LIVE_GATEWAY_FILE:
                        violations.append(f"{rel}:{lineno}: {stripped}")

        assert not violations, (
            "rich.live.Live 在 ui/render.py 外被导入（违反强制网关）:\n"
            + "\n".join(violations)
            + "\n\n请将 Live 使用下沉到 ui/render.StreamingRenderer，或改用 StreamingRenderer。"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
