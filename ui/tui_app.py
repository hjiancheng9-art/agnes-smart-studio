"""CRUX TUI Application — AI programming assistant terminal."""

from __future__ import annotations

import concurrent.futures
import io
import logging
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import BeforeInput

from ui.clipboard_image import detect_drag_images, get_clipboard_image, is_image_path
from ui.message_pane import MessagePane
from ui.status_bar import StatusBar
from ui.theme import build_style
from ui.ui_heartbeat import CdpSafeExecutor, MouseModeGuard, UIHeartbeat

if TYPE_CHECKING:
    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI

_TL, _TR, _BL, _BR, _H, _V = "┌", "┐", "└", "┘", "─", "│"


def _tw() -> int:
    try:
        return max(shutil.get_terminal_size().columns, 40)
    except Exception:
        return 80


class TuiApp:
    def __init__(
        self,
        session: ChatSession,
        cli: CruxCLI,
        *,
        session_wire=None,
        startup_banner: str = "",
    ) -> None:
        self.session = session
        self.cli = cli
        self.wire = session_wire
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._thinking = False
        self._last_invalidate = 0.0  # throttle rendering during streaming

        self.message_pane = MessagePane()
        self.status_bar = StatusBar(model_fn=lambda: self.session.model, cwd=Path.cwd())

        self._history = InMemoryHistory()
        self.input_buffer = Buffer(
            multiline=False,
            accept_handler=self._on_accept,
            history=self._history,
        )

        self.kb = KeyBindings()

        # ── UI Heartbeat + CDP Safe Executor + Mouse Mode Guard ──
        self.heartbeat = UIHeartbeat()
        self.safe_cdp = CdpSafeExecutor(heartbeat=self.heartbeat)
        self.mouse_guard = MouseModeGuard()
        self.mouse_guard.enable()
        self._heartbeat_started = False
        # Wire mouse_guard to message pane for auto-restore on scroll
        self.message_pane._mouse_guard = self.mouse_guard

        @self.kb.add("c-c")
        def _(event):
            event.app.exit()

        @self.kb.add("escape", "c-m")  # Alt+Enter: insert newline
        @self.kb.add("c-j")  # Ctrl+J: insert newline (alternative)
        def _(event):
            buf = self.input_buffer
            buf.insert_text("\n")

        @self.kb.add("c-v")
        def _(event):
            img_path = get_clipboard_image()
            if img_path:
                self._send_image(img_path)
            else:
                self.input_buffer.paste_from_clipboard(event.app.clipboard.get_data())

        @self.kb.add("c-y")  # Ctrl+Y: copy last response to clipboard
        def _(event):
            texts = [t for style, t in self.message_pane._lines if "[CRUX]" in t]
            if texts:
                last = texts[-1].replace("[CRUX] ", "")
                event.app.clipboard.set_data(last)
                self.message_pane.append_info("已复制到剪贴板")

        @self.kb.add("escape")
        def _(event):
            self.input_buffer.reset()

        @self.kb.add("c-l")
        def _(event):
            self.message_pane.clear()
            event.app.invalidate()

        @self.kb.add("f11")
        def _(event):
            """Toggle full-screen / windowed mode."""
            renderer = event.app.renderer
            renderer.full_screen = not renderer.full_screen
            if not renderer.full_screen and renderer._in_alternate_screen:
                renderer.output.quit_alternate_screen()
                renderer._in_alternate_screen = False
            # Force full redraw
            event.app.renderer.reset(leave_alternate_screen=not renderer.full_screen)
            event.app.invalidate()

        @self.kb.add("pageup")
        def _(event):
            self.message_pane.scroll_page_up()
            event.app.invalidate()

        @self.kb.add("pagedown")
        def _(event):
            self.message_pane.scroll_page_down()
            event.app.invalidate()

        @self.kb.add("home")
        def _(event):
            self.message_pane.scroll_to_top()
            event.app.invalidate()

        @self.kb.add("end")
        def _(event):
            self.message_pane.scroll_to_bottom()
            event.app.invalidate()

        @self.kb.add("c-home")
        def _(event):
            self.message_pane.scroll_to_top()
            event.app.invalidate()

        @self.kb.add("c-up")
        def _(event):
            self.message_pane.scroll_up(1)
            event.app.invalidate()

        @self.kb.add("c-down")
        def _(event):
            self.message_pane.scroll_down(1)
            event.app.invalidate()

        @self.kb.add("c-end")
        def _(event):
            self.message_pane.scroll_to_bottom()
            event.app.invalidate()

        # Mouse wheel scrolling
        @self.kb.add(Keys.ScrollUp)
        def _(event):
            self.message_pane.scroll_up(5)
            event.app.invalidate()

        @self.kb.add(Keys.ScrollDown)
        def _(event):
            self.message_pane.scroll_down(5)
            event.app.invalidate()

        self._app = self._make_app()

        if startup_banner:
            self.message_pane.append_info(startup_banner)

        # Activity log: (icon, style_class, message) per entry
        # Persists until next user message. Always visible.
        self._activity_log: list[tuple[str, str, str]] = []

    # ── Layout ──────────────────────────────────────────────

    def _make_app(self) -> Application:
        # Activity pane — shows all tool calls, thinking steps, and status
        def _activity_content():
            if not self._activity_log:
                return FormattedText([])
            pieces = []
            for icon, style_class, msg in self._activity_log:
                pieces.append((style_class, f" {icon} {msg}"))
                pieces.append(("", "\n"))
            if pieces:
                pieces.pop()  # remove trailing newline
            return FormattedText(pieces)

        activity_window = Window(
            content=FormattedTextControl(_activity_content),
            height=lambda: min(8, len(self._activity_log)) if self._activity_log else 0,
            style="class:message-area",
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        def _prompt():
            return f"{_V} {'*' if self._thinking else '>'} "

        input_ctrl = BufferControl(
            buffer=self.input_buffer,
            input_processors=[BeforeInput(_prompt)],
            focusable=True,
        )

        root = HSplit(
            [
                # Message zone (top, fills)
                self.message_pane.pane,
                # Separator (always visible when there's activity)
                Window(
                    content=FormattedTextControl(
                        lambda: (
                            FormattedText([("class:input-border", _H * _tw())])
                            if self._activity_log
                            else FormattedText([])
                        )
                    ),
                    height=lambda: 1 if self._activity_log else 0,
                    style="class:input-border",
                    always_hide_cursor=True,
                ),
                # Activity zone (tool calls, thinking steps, status)
                activity_window,
                # Input
                Window(
                    content=input_ctrl,
                    height=lambda: min(10, max(1, 1 + self.input_buffer.text.count("\n"))),
                    style="class:input-field",
                ),
                # Status bar
                Window(
                    content=FormattedTextControl(lambda: self.status_bar.render()),
                    height=1,
                    style="class:status-bar",
                    always_hide_cursor=True,
                ),
            ]
        )

        return Application(
            layout=Layout(root),
            key_bindings=self.kb,
            style=build_style(),
            full_screen=True,
            mouse_support=True,
        )

    # ── Input ───────────────────────────────────────────────

    def _on_accept(self, buf: Buffer) -> bool:
        text = buf.text.strip()
        buf.reset()
        if not text:
            return True
        # ── Drag-drop detection: pasted file paths → treat as images ──
        drag_images = detect_drag_images(text)
        if drag_images and len(drag_images) == 1:
            self._send_image(drag_images[0])
            return True
        if drag_images:
            for img in drag_images:
                self._send_image(img)
            return True
        # ── Single image path? ──
        single_path = is_image_path(text)
        if single_path:
            self._send_image(single_path)
            return True
        if text in ("/q", "/quit", "/exit"):
            self._app.exit()
            return True
        # ── Theme switcher ──
        if text == "/theme":
            from ui.theme import THEMES, get_active_theme

            C = get_active_theme()
            cur_name = C["name"]
            out = [f"🎨 当前主题: {cur_name} — {C['desc']}", "可用主题:"]
            for tid, t in THEMES.items():
                marker = "▸ " if t["name"] == cur_name else "  "
                out.append(f"  {marker}{tid}: {t['name']} — {t['desc']}")
            out.append("切换: /theme <名称>")
            self.message_pane.append_info("\n".join(out))
            return True
        if text.startswith("/theme "):
            name = text.split(" ", 2)[1].strip()
            from ui.theme import THEMES, build_style, set_theme

            if name in THEMES:
                set_theme(name)
                self._app.style = build_style()
                self.message_pane.append_info(f"✅ 已切换至: {THEMES[name]['name']} — {THEMES[name]['desc']}")
            else:
                self.message_pane.append_info(f"❌ 未知主题: {name}  可用: {', '.join(THEMES.keys())}")
            return True
        if text.startswith("/"):
            _buf = io.StringIO()
            _old = sys.stdout
            sys.stdout = _buf
            try:
                handled = self.cli.dispatch(text)
            finally:
                sys.stdout = _old
            out = _buf.getvalue().rstrip()
            if out:
                self.message_pane.append_info(out)
            if not handled and not out:
                self.message_pane.append_info(f"Unknown command: {text}  — /help for commands")
            return True
        if self._thinking:
            self.message_pane.append_info("Please wait — still processing previous request")
            return True
        self._activity_log.clear()
        self._thinking_buf = ""
        self.message_pane.append_message("user", text)
        self.message_pane.scroll_to_bottom()
        self._thinking = True
        self._ui(self._refresh_status, _force=True)
        self._executor.submit(self._stream_response, text)
        return True

    def _send_image(self, image_path: str) -> None:
        """Send an image file for vision analysis. Dispatched from paste or drag-drop."""
        import os

        if self._thinking:
            self.message_pane.append_info("Please wait — still processing previous request")
            return
        self._activity_log.clear()
        fname = os.path.basename(image_path)
        self.message_pane.append_message("user", f"[图片: {fname}]")
        self.message_pane.scroll_to_bottom()
        self._thinking = True
        self._refresh_status()
        self._executor.submit(self._stream_image_response, image_path)

    def _stream_image_response(self, image_path: str) -> None:
        """Stream vision response for an image file."""
        try:
            prompt = "请详细描述这张图片的内容。如果是截图，请描述界面、文字和关键信息。"
            self._ui(self.message_pane.stream_start, "crux")
            self._activity_log.append(("●", "class:message-tool", f"视觉分析: {os.path.basename(image_path)}"))
            for kind, payload in self.session.send_stream(prompt, image_url=image_path):
                if kind == "text":
                    self._ui(self.message_pane.stream_append, str(payload))
                elif kind == "info":
                    self._ui(self.message_pane.append_info, str(payload))
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
            # Mark vision complete
            if self._activity_log:
                last_icon, _, last_msg = self._activity_log[-1]
                if "●" in last_icon:
                    self._activity_log[-1] = ("✓", "class:success", last_msg.replace("视觉分析: ", "视觉分析完成: "))
            self._ui(self.message_pane.stream_end, _force=True)
            self._ui(self.message_pane.scroll_to_bottom, _force=True)
        except Exception as e:
            self._ui(self.message_pane.append_error, f"图片分析失败: {e}", _force=True)
            self._activity_log.append(("✗", "class:message-error", f"视觉分析失败: {e}"))
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            self._thinking = False
            self._ui(self._refresh_status, _force=True)

    def _stream_response(self, user_text: str) -> None:
        try:
            self._ui(self.message_pane.stream_start, "crux")
            pending_tool = None  # track current tool name for status updates
            _t0 = time.monotonic()
            _first_token = False
            for kind, payload in self.session.send_stream(user_text):
                if not _first_token and kind in ("text", "thinking"):
                    _first_token = True
                    self.status_bar.set_latency(time.monotonic() - _t0)
                if kind == "text":
                    self._ui(self.message_pane.stream_append, str(payload))
                elif kind == "thinking":
                    # Accumulate thinking chunks into a single activity log entry
                    chunk = str(payload)
                    if not hasattr(self, "_thinking_buf"):
                        self._thinking_buf = ""
                    if not self._thinking_buf:
                        self._activity_log.append(("●", "class:message-thinking", chunk[:120]))
                    else:
                        # Update last entry — append new text
                        merged = self._thinking_buf + chunk
                        if len(merged) > 120:
                            merged = merged[:117] + "..."
                        if self._activity_log and "class:message-thinking" in self._activity_log[-1][1]:
                            self._activity_log[-1] = ("●", "class:message-thinking", merged)
                    self._thinking_buf += chunk
                    self._ui(lambda: None)
                elif kind == "info":
                    msg = str(payload).strip()
                    if not msg:
                        continue
                    # Tool start
                    if msg.startswith("正在执行 "):
                        tool_name = msg[5:].rstrip(".")
                        pending_tool = tool_name
                        self._activity_log.append(("●", "class:message-tool", f"执行 {tool_name}"))
                    elif msg.startswith("正在生成"):
                        action = msg[2:].rstrip(".")
                        pending_tool = action
                        self._activity_log.append(("●", "class:message-tool", f"生成 {action}"))
                    elif "执行完成" in msg:
                        # Mark last pending tool as done
                        if pending_tool and self._activity_log:
                            last_icon, _, last_msg = self._activity_log[-1]
                            if "●" in last_icon:
                                self._activity_log[-1] = (
                                    "✓",
                                    "class:success",
                                    last_msg.replace("执行 ", "").replace("生成 ", ""),
                                )
                        pending_tool = None
                    elif "fallback" in msg.lower() or "连接中断" in msg:
                        self._activity_log.append(("⚠", "class:message-error", msg[:100]))
                    elif "预算" in msg:
                        self._activity_log.append(("💰", "class:message-info", msg[:100]))
                    else:
                        self._activity_log.append(("·", "class:message-info", msg[:120]))
                    self._ui(lambda: None)
                elif kind == "tool_result":
                    # Tool completed successfully
                    if pending_tool and self._activity_log:
                        last_icon, _, last_msg = self._activity_log[-1]
                        if "●" in last_icon:
                            self._activity_log[-1] = (
                                "✓",
                                "class:success",
                                last_msg.replace("执行 ", "").replace("生成 ", ""),
                            )
                    pending_tool = None
                    self._ui(lambda: None)
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
                    self._activity_log.append(("✗", "class:message-error", str(payload)[:120]))
                elif kind in ("image", "video"):
                    d = payload if isinstance(payload, dict) else {}
                    loc = d.get("local_path", "") or d.get("url", "") or d.get("video_url", "")
                    if loc:
                        self._ui(self.message_pane.append_info, f"Saved: {loc}")
                        self._activity_log.append(("✓", "class:success", f"已保存: {loc}"))
            # Mark any remaining pending tool as done
            if pending_tool and self._activity_log:
                last_icon, _, last_msg = self._activity_log[-1]
                if "●" in last_icon:
                    self._activity_log[-1] = ("✓", "class:success", last_msg.replace("执行 ", "").replace("生成 ", ""))
            self._ui(self.message_pane.stream_end, _force=True)
            self._ui(self.message_pane.scroll_to_bottom, _force=True)
        except Exception as e:
            self._ui(self.message_pane.append_error, str(e), _force=True)
            self._activity_log.append(("✗", "class:message-error", f"异常: {e}"))
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            self._thinking = False
            self._ui(self._refresh_status, _force=True)
        if self.wire:
            try:
                self.wire.record_turn("assistant", "[streamed]")
            except Exception:
                logging.getLogger("crux.tui").debug("wire.record_turn failed", exc_info=True)

    def _ui(self, fn, *a, _force: bool = False):
        _log = logging.getLogger("crux.tui")
        self.heartbeat.tick()  # mark UI activity
        try:
            if a:
                fn(*a)
            else:
                fn()
        except Exception:
            _log.warning("TUI _ui callback failed", exc_info=True)
        try:
            if self._app and self._app.is_running:
                now = time.monotonic()
                # Throttle: during streaming, skip redraws within 30ms (~30fps)
                if _force or not self._thinking or now - self._last_invalidate > 0.030:
                    self._last_invalidate = now
                    self._app.invalidate()
        except Exception:
            _log.warning("TUI _ui invalidate failed", exc_info=True)

    def _refresh_status(self):
        self.status_bar.set_model(self.session.model)
        self.status_bar.set_thinking(self._thinking)
        try:
            chars = sum(len(str(m.get("content", ""))) for m in self.session.messages)
            self.status_bar.set_context(int(chars * 0.4), 128000)
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)
        self.status_bar.refresh()

    def run(self):
        try:
            # Start heartbeat monitoring
            self.heartbeat.start()
            self._heartbeat_started = True
            # Restore mouse mode in case it was lost during startup
            self.mouse_guard.restore()
            logger.info("CRUX TUI started with heartbeat + mouse_guard")
            self._app.run()
        except Exception as e:
            print(f"TUI error: {e}", file=sys.stderr)
            traceback.print_exc()
        finally:
            if self._heartbeat_started:
                self.heartbeat.stop()
                logger.info("CRUX TUI shutdown — heartbeat stopped")
            self._executor.shutdown(wait=False)
