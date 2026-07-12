"""CRUX TUI v2 — Seven Beasts Command Center.

Terminal-aesthetic AI chat interface featuring:
- Seven Beasts themed color system (虎/龙/雀/武/麟/蛇/翼)
- Pixel-art welcome screen integrated into message area
- Animated braille spinner activity bar
- Collapsible thinking panel for model reasoning
- Box-drawing message bubbles
- Multi-line input with command completion

Architecture:
  Reuses MessagePane (ui/message_pane.py) and StatusBar (ui/status_bar.py)
  unchanged, composing them into a richer visual layout.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import io
import logging
import os
import shutil
import sys
import sys as _sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output

# ── Control Plane ─────────────────────────────────────────
from core.control_plane import ControlEventType, control
from core.protocol import emit_state

# ── Static imports (avoid per-frame re-import) ──
from core.version import __version__ as _CRUX_VERSION
from ui.animation_gov import AnimationGovernor
from ui.clipboard_image import detect_drag_images, get_clipboard_image, is_image_path
from ui.completer import TuiCompleter
from ui.copy_manager import CopyManager
from ui.dashboard import DashboardState
from ui.input_router import InputRouter, get_clipboard
from ui.message_detail import MessageDetailScreen
from ui.message_pane import MessagePane
from ui.message_store import MessageStore
from ui.panels.incident_panel import load_incidents, render_incidents
from ui.panels.provider_route_panel import render_provider_route

# ── Panels ──
from ui.panels.run_summary_panel import render_run_summary
from ui.responsive import EnvironmentInfo, LayoutManager
from ui.status_bar import StatusBar
from ui.theme_v2 import build_style_v2
from ui.widgets_v2 import Spinner, ThinkingPanel, build_welcome_formatted, context_bar

try:
    from core.methodology import get_methodology_state as _get_methodology_state
except ImportError:
    _get_methodology_state = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI

logger = logging.getLogger("crux.tui_v2")


def _tw() -> int:
    try:
        return max(shutil.get_terminal_size().columns, 40)
    except Exception:
        return 80


# ── Screen system ────────────────────────────────────────────────


class Screen:
    """Base class for a TUI screen (one view mode at a time)."""

    name: str = "screen"

    def render(self, tw: int):
        return []

    def on_enter(self, app):
        pass

    def on_exit(self, app):
        pass

    def handle_key(self, key: str) -> bool:
        return False


class ScreenStack:
    """Manages navigation between screens."""

    def __init__(self):
        self._stack = []

    @property
    def current(self):
        return self._stack[-1] if self._stack else None

    @property
    def active(self):
        return len(self._stack) > 0

    def push(self, screen, app):
        self._stack.append(screen)
        if app is not None:
            screen.on_enter(app)

    def pop(self, app):
        if not self._stack:
            return None
        s = self._stack.pop()
        if app is not None:
            s.on_exit(app)
        return s

    def pop_all(self, app):
        while self._stack:
            self.pop(app)


class DashboardScreen(Screen):
    """Full-screen dashboard overlay. Delegates to problem-oriented DashboardState."""

    name = "dashboard"

    def __init__(self):
        self._cached = []

    def on_enter(self, app):
        if app and hasattr(app, "_dash_state"):
            app._dash_state.set_state("active")
        if app:
            app._app.invalidate()

    def __pt_formatted_text__(self):
        from ui.dashboard import render_dashboard

        try:
            state = getattr(self, '_dash_state_ref', None)
            layout_mgr = getattr(self, '_layout_mgr_ref', None)
            layout = layout_mgr.config if layout_mgr else None
            result = render_dashboard(state=state, layout=layout)
            from prompt_toolkit.formatted_text import FormattedText

            return FormattedText(result)
        except Exception:
            from prompt_toolkit.formatted_text import FormattedText

            return FormattedText([("class:dim", "Dashboard loading...")])


class IncidentLogScreen(Screen):
    name = "incidents"

    def __init__(self):
        self._incidents = []

    def on_enter(self, app):
        try:
            from core.incident_store import load_incidents

            self._incidents = load_incidents(limit=50)
        except Exception:
            self._incidents = []

    def render(self, tw):
        ft = []
        ft.append(("bold", f"{'=' * tw}\n"))
        ft.append(("bold class:header", "  INCIDENT LOG\n"))
        ft.append(("class:dim", f"  {tw * '-'}\n"))
        if not self._incidents:
            ft.append(("class:dim", "  (no incidents recorded)\n"))
        else:
            ft.append(("class:dim", f"  {'ID':<16} {'Category':<18} {'Sev':<6} {'Time'}\n"))
            for inc in self._incidents[:25]:
                iid = str(inc.get("incident_id", "?"))[:16]
                cat = str(inc.get("category", "?"))[:18]
                sev = str(inc.get("severity", "?"))[:6]
                ts = str(inc.get("timestamp", "?"))[:16]
                ft.append(("", f"  {iid:<16} {cat:<18} {sev:<6} {ts}\n"))
        ft.append(("class:dim", "\n  Esc: exit\n"))
        return ft


class RemediationScreen(Screen):
    name = "remediate"

    def __init__(self):
        self._cats = []
        self._pb = None
        self._results = []

    def on_enter(self, app):
        try:
            from core.incident_playbook import PLAYBOOKS

            self._cats = list(PLAYBOOKS.keys())
        except Exception:
            self._cats = []
        self._results = []

    def select(self, cat):
        try:
            from core.incident_playbook import get_playbook

            self._pb = get_playbook(cat)
        except Exception:
            self._pb = None

    def run(self, iid):
        try:
            from core.incident_store import load_incidents

            incs = load_incidents(limit=100)
            inc = next((x for x in incs if x.get("incident_id", x.get("_id", "")) == iid), None)
            if inc:
                from core.remediation_executor import remediate_incident

                self._results = remediate_incident(inc)
            else:
                self._results = [{"status": "failed", "command": iid, "risk": "?", "message": "not found"}]
        except Exception as e:
            self._results = [{"status": "failed", "command": iid, "risk": "?", "error": str(e)}]

    def back(self):
        self._pb = None
        self._results = []

    def render(self, tw):
        ft = []
        ft.append(("bold", f"{'=' * tw}\n"))
        if self._results:
            ft.append(("bold class:header", "  REMEDIATION RESULTS\n"))
            for r in self._results:
                ic = (
                    chr(10003)
                    if r["status"] == "success"
                    else chr(8857)
                    if r["status"] == "pending_approval"
                    else chr(10007)
                )
                ft.append(("", f"    {ic} {r.get('command', '?'):35s} {r['status']}\n"))
            if self._results[-1].get("message"):
                ft.append(("class:status-warn", f"    >> {self._results[-1]['message']}\n"))
            ft.append(("class:dim", "\n  Esc: back\n"))
            return ft
        if self._pb:
            ft.append(("bold class:header", f"  {self._pb.get('title', '?')}\n"))
            sev = self._pb.get("severity", "?")
            sev_cls = "class:status-err" if sev == "critical" else "class:status-warn"
            ft.append((sev_cls, f"  severity: {sev}\n\n"))
            for i, s in enumerate(self._pb.get("steps", []), 1):
                ft.append(("", f"    {i}. {s}\n"))
            auto = self._pb.get("auto_commands", [])
            if auto:
                ft.append(("bold", "\n  Auto-fix commands:\n"))
                for c in auto:
                    ft.append(("class:dim", f"    $ {c}\n"))
            ft.append(("class:dim", "\n  /remediate run <id>  |  Esc: list\n"))
        else:
            ft.append(("bold class:header", "  PLAYBOOKS\n"))
            ft.append(("class:dim", f"  {tw * '-'}\n"))
            for c in self._cats[:20]:
                ft.append(("", f"    {c}\n"))
            ft.append(("class:dim", "\n  /remediate <cat> | /remediate run <id>\n"))
        return ft


class RunReplayScreen(Screen):
    name = "replay"

    def __init__(self):
        self._records = []
        self._selected = None

    def on_enter(self, app):
        try:
            from core.run_replay import list_replays

            self._records = list_replays(limit=20)
        except Exception:
            self._records = []

    def select(self, rid):
        try:
            from core.run_replay import load_replay

            self._selected = load_replay(rid)
        except Exception:
            self._selected = None

    def back(self):
        self._selected = None

    def render(self, tw):
        ft = []
        ft.append(("bold", f"{'=' * tw}\n"))
        ft.append(("bold class:header", "  RUN REPLAYS\n"))
        ft.append(("class:dim", f"  {tw * '-'}\n"))
        if not self._records:
            ft.append(("class:dim", "  (no replay records)\n"))
        else:
            ft.append(("class:dim", f"  {'Root ID':<24} {'Status':<12} {'Time'}\n"))
            for r in self._records[:20]:
                rid = str(r.get("root_trace_id", "?"))[:24]
                st = str(r.get("status", "?"))[:12]
                ts = str(r.get("saved_at", "?"))[:12]
                ft.append(("", f"  {rid:<24} {st:<12} {ts}\n"))
        ft.append(("class:dim", "\n  Esc: exit\n"))
        return ft


class ApprovalScreen(Screen):
    name = "approval"

    def __init__(self):
        self._pending = []

    def on_enter(self, app):
        try:
            from ui.tui_v2 import _APPROVAL_PENDING

            self._pending = list(_APPROVAL_PENDING)
        except Exception:
            self._pending = []

    def render(self, tw):
        ft = []
        ft.append(("bold", f"{'=' * tw}\n"))
        ft.append(("bold class:header", "  PENDING APPROVALS\n"))
        ft.append(("class:dim", f"  {tw * '-'}\n"))
        if not self._pending:
            ft.append(("class:dim", "  (no pending approvals)\n"))
        else:
            for item in self._pending:
                if item.get("status") == "pending":
                    risk = item.get("risk", "?")
                    cls = "class:status-err" if risk == "critical" else "class:status-warn"
                    ft.append((cls, f"  [{risk.upper()}] {item.get('command', '?')}\n"))
                    ft.append(("", f"    {item.get('description', '')}\n"))
        ft.append(("class:dim", "\n  Esc: exit\n"))
        return ft


_APPROVAL_PENDING = []


def request_approval(action, desc, risk="high"):
    _APPROVAL_PENDING.append({"action": action, "description": desc, "risk": risk, "status": "pending"})
    return False


# ── TUI App ─────────────────────────────────────────────────────
class TuiAppV2:
    """Seven Beasts Command Center — redesigned terminal TUI.

    Layout (top → bottom):
      ╔ Header Bar ╗  — CRUX branding, model, latency
      ║ Messages  ║  — chat bubbles + welcome screen (empty state)
      ║ Thinking  ║  — collapsible model reasoning panel
      ║ Activity  ║  — animated tool execution status bar
      ║ Input     ║  — framed input box with command hints
      ╚ Status    ╝  — model, git, methodology level, context bar
    """

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
        self._streaming = False
        # ── Control Plane ──
        self._pending_msg_id: str | None = None
        self._pending_text: str = ""
        self._pending_timer: threading.Thread | None = None
        self._last_control_status: str = ""
        self._msg_store = MessageStore()
        self._copy_mgr = CopyManager(self._msg_store)
        self._detail_view: MessageDetailScreen | None = None
        self._input_router = InputRouter()
        self._clipboard = get_clipboard()
        self._native_select: bool = False
        self._cancel_requested: bool = False
        self._interrupted_by_priority: bool = False
        # ── Responsive Layout & Animation Governance (per 3-platform debate) ──
        self._env = EnvironmentInfo.detect()
        self._layout_mgr = LayoutManager(env=self._env)
        # Default to blade palette on truecolor terminals
        if self._env.has_truecolor and not self._env.is_ssh:
            self._layout_mgr._override_theme = "blade"
        self._anim_gov = AnimationGovernor(ssh_mode=self._env.is_ssh)
        self._current_layout = self._layout_mgr.config
        # ── React to layout/environment changes ──
        self._layout_mgr.on_change(self._on_layout_changed)
        # ── Focus Mode: hide chrome, show only messages (F12 toggle) ──
        self._focus_mode = False
        # ── Problem-Oriented Dashboard State (per debate: quiet normally, speak up on problems) ──
        self._dash_state = DashboardState()

        self._latency: float | None = None
        self._state_lock = threading.Lock()

        # ── Cached values (updated in _refresh_status, read by render) ──
        self._cached_git = ""
        self._cached_ctx_pct = 0.0
        self._show_dashboard = False

        # ── Core components ──
        self.message_pane = MessagePane()
        self.status_bar = StatusBar(model=session.model, cwd=Path.cwd())
        # Mouse mode guard: auto-restore terminal mouse mode after subprocess damage
        try:
            from ui.ui_heartbeat import MouseModeGuard
            self._mouse_guard = MouseModeGuard()
            self._mouse_guard.enable()
            self.message_pane._mouse_guard = self._mouse_guard
        except Exception:
            self._mouse_guard = None
        # ── Screen system ──
        self.screen_stack = ScreenStack()
        self._available_screens = {
            "dashboard": DashboardScreen(),
            "incidents": IncidentLogScreen(),
            "remediate": RemediationScreen(),
            "replay": RunReplayScreen(),
            "approval": ApprovalScreen(),
        }
        self.thinking_panel = ThinkingPanel()

        # ── Activity log: [(icon, style_class, message), ...] ──
        self._activity_log: list[tuple[str, str, str]] = []
        self._activity_lock = threading.RLock()
        self._activity_log_limit = 500
        self._activity_render_limit = 100
        self._activity_expanded = False
        self._activity_collapsed_height = 3
        self._activity_expanded_height = 8
        self._queued_text: str | None = None

        # ── Spinner ──
        self._spinner = Spinner(on_tick=self._on_spinner_tick)

        # ── Animation timer (independent of spinner, always running) ──
        self._anim_running = False

        # ── Dashboard mode ──
        self._dashboard_mode = False
        self._normal_container = None  # set in _make_app after building root

        # ── Welcome screen ──
        self._setup_welcome()

        # ── Input ──
        self._history = InMemoryHistory()
        self._completer = TuiCompleter()
        self.input_buffer = Buffer(
            multiline=True,
            accept_handler=self._on_accept,
            history=self._history,
            completer=self._completer,
        )

        # ── Key bindings ──
        self.kb = self._setup_keybindings()

        # ── Build app ──
        self._last_invalidate = 0.0
        self._invalidate_failed_once = False
        self._app = self._make_app()

        # ── Download manager ──
        from core.download.manager import get_manager

        self._dl_manager = get_manager()
        self._dl_manager.on_update(self._on_download_update)

        # Welcome screen replaces banner — see _setup_welcome()

    # ══════════════════════════════════════════════════════════════
    #  Welcome screen setup
    # ══════════════════════════════════════════════════════════════

    def _setup_welcome(self) -> None:
        """Configure the welcome screen as the message pane's empty state."""
        model_name = self.session.model
        cwd = str(Path.cwd())
        branch = ""
        try:
            import subprocess

            r = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            branch = r.stdout.strip()
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        def _welcome_renderer() -> FormattedText:
            palette = None
            try:
                from ui.theme_v2 import PALETTES

                mode = self._layout_mgr.theme_mode
                palette = PALETTES.get(mode)
            except Exception:
                palette = None
            return build_welcome_formatted(
                model_name=model_name,
                cwd=cwd,
                branch=branch,
                palette=palette,
            )

        self.message_pane.set_empty_renderer(_welcome_renderer)

    # ══════════════════════════════════════════════════════════════
    #  Key bindings
    # ══════════════════════════════════════════════════════════════

    def _setup_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # (Ctrl+C handled below at second binding)
        def _(event):
            with self._state_lock:
                streaming = self._streaming or self._thinking
            if streaming:
                self._cancel_current_response()
                self._log_append(("\u25a0", "class:activity-warn", "已请求中断当前响应"))
                event.app.invalidate()
                return
            self._log_append(("\u2022", "class:activity-info", "按 Ctrl+Q 退出 CRUX"))
            event.app.invalidate()

        @kb.add("c-q")
        def _(event):
            self._request_exit()
            event.app.exit()

        @kb.add("escape", "enter")  # Alt+Enter: insert newline
        @kb.add("c-j")  # Ctrl+J: insert newline (alternative)
        def _(event):
            self.input_buffer.insert_text("\n")

        @kb.add("enter")
        def _(event):
            """Enter: submit message. Alt+Enter / Ctrl+J to insert newline."""
            event.current_buffer.validate_and_handle()

        @kb.add("c-v")
        def _(event):
            img_path = get_clipboard_image()
            if img_path:
                self._send_image(img_path)
            else:
                self.input_buffer.paste_from_clipboard(event.app.clipboard.get_data())

        @kb.add("escape", "escape")  # Double-Escape: clear input (avoids Alt+Enter conflict)
        def _(event):
            self.input_buffer.reset()
            event.app.invalidate()

        @kb.add("c-l")
        def _(event):
            self.message_pane.clear()
            self._log_clear()
            self.thinking_panel.clear()
            event.app.invalidate()

        @kb.add("c-t")
        def _(event):
            """Toggle thinking panel pin state."""
            self.thinking_panel.toggle_pin()
            event.app.invalidate()

        @kb.add("c-k")
        def _(event):
            """Clear current input."""
            self.input_buffer.reset()
            event.app.invalidate()

        @kb.add("c-m")
        def _(event):
            """Toggle secondary metrics panel (CPU/memory/disk)."""
            # Ctrl+M == Enter in many terminals — don't intercept when typing
            if event.app.current_buffer is self.input_buffer:
                event.current_buffer.validate_and_handle()
                return
            self._dash_state.toggle_secondary()
            event.app.invalidate()

        @kb.add("f11")
        def _(event):
            pass

        @kb.add("f12")
        def _(event):
            """Toggle focus mode: hide all chrome, show only messages."""
            app = event.app
            renderer = event.app.renderer
            self._focus_mode = not self._focus_mode
            if self._focus_mode:
                self.message_pane._pinned = True
            app.invalidate()
            self.message_pane._auto_scroll()
            if not renderer.full_screen and renderer._in_alternate_screen:
                renderer.output.quit_alternate_screen()
                renderer._in_alternate_screen = False
            event.app.renderer.reset(leave_alternate_screen=not renderer.full_screen)
            event.app.invalidate()

        def _(event):
            self.message_pane.scroll_page_up()
            event.app.invalidate()

        @kb.add("pagedown")
        def _(event):
            self.message_pane.scroll_page_down()
            event.app.invalidate()

        # Note: plain Home/End are consumed by the multiline Buffer for cursor
        # movement. Use Ctrl+Home / Ctrl+End to jump to top/bottom instead.

        @kb.add("c-home", eager=True)
        def _(event):
            self.message_pane.scroll_to_top()
            event.app.invalidate()

        @kb.add("c-end", eager=True)
        def _(event):
            self.message_pane.scroll_to_bottom()
            event.app.invalidate()

        @kb.add("pageup", eager=True)
        def _(event):
            self.message_pane.scroll_page_up()
            event.app.invalidate()

        @kb.add("pagedown", eager=True)
        def _(event):
            self.message_pane.scroll_page_down()
            event.app.invalidate()

        @kb.add(Keys.ScrollUp)
        def _(event):
            self.message_pane.scroll_up(5)
            event.app.invalidate()

        @kb.add("c-l")
        def _(event):
            """Ctrl+L: 强制重置滚动 + 恢复鼠标模式"""
            self.message_pane.scroll_to_bottom()
            self.message_pane._pinned = True
            # 恢复终端鼠标追踪
            if hasattr(event.app.output, 'enable_mouse_support'):
                event.app.output.enable_mouse_support()
            event.app.invalidate()

        @kb.add(Keys.ScrollDown)
        def _(event):
            self.message_pane.scroll_down(5)
            event.app.invalidate()

        # Alt+Up / Alt+Down: single-line scroll (plain Up/Down reserved for history)
        @kb.add("escape", "up")
        def _(event):
            self.message_pane.scroll_up(1)
            event.app.invalidate()

        @kb.add("escape", "down")
        def _(event):
            self.message_pane.scroll_down(1)
            event.app.invalidate()

        # ── Streaming guards ──
        # When streaming, up/down only move cursor, don't trigger history

        _is_streaming = Condition(lambda: self._streaming)

        @kb.add("up", filter=_is_streaming)
        def _(event):
            with contextlib.suppress(Exception):
                event.current_buffer.cursor_up()

        @kb.add("down", filter=_is_streaming)
        def _(event):
            with contextlib.suppress(Exception):
                event.current_buffer.cursor_down()

        @kb.add("f8")
        def _(event):
            self._activity_expanded = not self._activity_expanded
            event.app.invalidate()

        # ── Control Plane 快捷键 ──
        @kb.add("c-z")
        def _ctrl_z(event):
            """Ctrl+Z: 撤销 pending 消息。"""
            self._undo_pending()

        # (Ctrl+C handled below at second binding)
        def _ctrl_c(event):
            """Ctrl+C: 取消当前 run。"""
            with self._state_lock:
                is_streaming = self._streaming
            if is_streaming:
                control().cancel_run("用户 Ctrl+C 取消")
                self._cancel_current_response()
            else:
                raise KeyboardInterrupt()

        @kb.add("escape")
        def _esc(event):
            """Esc: 退出详情 / 退出焦点模式 / 退出复制模式 / 暂停当前 run。"""
            if self._detail_view and self._detail_view.active:
                self._detail_view.close()
                return
            if self._focus_mode:
                self._focus_mode = False
                self.message_pane._pinned = True
                self._ui(self._refresh_status)
                event.app.invalidate()
                return
            if getattr(self, '_copy_mode', False):
                self._copy_mode = False
                self._ui(self._refresh_status)
                event.app.invalidate()
                return
            if control().runs.is_running:
                control().pause_run("用户按 Esc 暂停")
                self._log_append(("→", "class:activity-warn", "执行已暂停（Esc）"))

        @kb.add("c-y")
        def _ctrl_y(event):
            """Ctrl+Y: 恢复暂停的 run。"""
            if control().runs.is_paused:
                control().runs.resume()
                self._log_append(("→", "class:activity-info", "执行已恢复（Ctrl+Y）"))

        # ══════════════════════════════════════════════════════════════
        #  Layout
        # ══════════════════════════════════════════════════════════════

        # ── Copy / Detail / Focus 快捷键 ──
        # 单字母快捷键：输入框聚焦时放行字符，不拦截
        def _typing(event):
            """True if user is typing in the input buffer — let char through."""
            return event.app.current_buffer is self.input_buffer

        @kb.add("c")
        def _copy_focused(event):
            """c: 复制聚焦消息全文。"""
            if _typing(event):
                event.current_buffer.insert_text("c")
                return
            if self._detail_view and self._detail_view.active:
                self._detail_view.handle_key("c")
                return
            # 无消息时不拦截，让 'c' 正常输入
            if not self._copy_mgr.has_messages():
                event.current_buffer.insert_text("c")
                return
            ok, msg = self._copy_mgr.copy_focused()
            icon, style = ("✓", "class:activity-done") if ok else ("✗", "class:error")
            self._log_append((icon, style, msg[:100]))
            self._ui(self._refresh_status)

        # ── Shift+C: 复制 Markdown ──
        @kb.add("C")
        def _copy_markdown(event):
            """Shift+C: 复制聚焦消息为 Markdown。"""
            if _typing(event):
                event.current_buffer.insert_text("C")
                return
            if not self._copy_mgr.has_messages():
                event.current_buffer.insert_text("C")
                return
            ok, msg = self._copy_mgr.copy_focused_markdown()
            icon, style = ("✓", "class:activity-done") if ok else ("✗", "class:error")
            self._log_append((icon, style, msg[:100]))
            self._ui(self._refresh_status)

        # ── F9: 原生选择模式 ──
        @kb.add("f9")
        def _native_select(event):
            """F9: 切换原生选择模式（TUI 暂停鼠标捕获）。"""
            self._native_select = not self._native_select
            if self._native_select:
                self._log_append(("→", "class:activity-warn", "原生选择模式：TUI 暂停鼠标，按 F9 返回"))
                self._ui(self._refresh_status)
            else:
                self._log_append(("→", "class:activity-info", "已恢复 TUI 鼠标控制"))
                self._ui(self._refresh_status)

        @kb.add("o")
        def _open_detail(event):
            """o: 打开消息详情视图。"""
            if _typing(event):
                event.current_buffer.insert_text("o")
                return
            idx = self._copy_mgr.focus.index
            if idx < 0 or idx >= len(self._msg_store):
                idx = len(self._msg_store) - 1
                self._copy_mgr.focus.index = idx
            if idx < 0:
                return  # empty store, nothing to open
            msg = self._msg_store.get(idx)
            self._detail_view = MessageDetailScreen(self._msg_store, idx)
            self._detail_view.on_close(lambda: self._ui(self._refresh_status))
            self._detail_view.open()
            snippet = msg.snippet(40) if msg else "(empty)"
            self._log_append(
                ("→", "class:activity-info", f"打开详情: 消息 #{idx} ({snippet}...)")
            )
            self._ui(self._refresh_status)

        @kb.add("up")
        def _focus_up(event):
            if self._detail_view and self._detail_view.active:
                self._detail_view.handle_key("up")
                self._ui(self._refresh_status)
                return
            # 焦点/复制模式：消息间导航
            in_focus = self._focus_mode
            in_copy = getattr(self, '_copy_mode', False)
            if in_focus or in_copy:
                msg = self._copy_mgr.store.get(self._copy_mgr.focus.prev())
                if msg:
                    self._log_append(("←", "class:activity-info", f"聚焦 [{msg.role}] {msg.snippet(80)}"))
                    self._ui(self._refresh_status)
                    return
            # 没有特殊模式 → 消息面板滚动
            self.message_pane._pinned = False
            self.message_pane.scroll_up(3)
            event.app.invalidate()

        @kb.add("down")
        def _focus_down(event):
            if self._detail_view and self._detail_view.active:
                self._detail_view.handle_key("down")
                self._ui(self._refresh_status)
                return
            # 焦点/复制模式：消息间导航
            in_focus = self._focus_mode
            in_copy = getattr(self, '_copy_mode', False)
            if in_focus or in_copy:
                msg = self._copy_mgr.store.get(self._copy_mgr.focus.next())
                if msg:
                    self._log_append(("→", "class:activity-info", f"聚焦 [{msg.role}] {msg.snippet(80)}"))
                    self._ui(self._refresh_status)
                    return
            # 没有特殊模式 → 消息面板滚动
            self.message_pane._pinned = False
            self.message_pane.scroll_down(3)
            event.app.invalidate()

        @kb.add("tab")
        def _focus_next_code(event):
            """Tab: 在代码块之间跳转。"""
            store = self._msg_store
            if not store or len(store) == 0:
                return
            idx = self._copy_mgr.focus.index
            if idx < 0 or idx >= len(store):
                idx = len(store) - 1
            msg = store.get(idx)
            if msg and msg.code_blocks:
                self._log_append(
                    ("→", "class:activity-info", f"代码块: {len(msg.code_blocks)} 个 — 按 c 复制当前")
                )
            self._ui(self._refresh_status)

        return kb

    def _make_app(self) -> Application:
        # ── Header Bar ──
        # Design: beast mascot (2s rotation) + brand | separator | model + heartbeat + clock
        _BEASTS = [
            ("class:status-bar-beast-baihu", "🐅"),
            ("class:status-bar-beast-qinglong", "🐉"),
            ("class:status-bar-beast-zhuque", "🦅"),
            ("class:status-bar-beast-xuanwu", "🐢"),
            ("class:status-bar-beast-qilin", "🦄"),
            ("class:status-bar-beast-tengshe", "🐍"),
            ("class:status-bar-beast-yinglong", "🐲"),
        ]
        _PULSE_DOTS = ["◎", "◉", "○", "◉"]

        def _header_content():
            tw = _tw()
            bstyle, bicon = _BEASTS[int(time.time() / 2.0) % 7]
            pulse = _PULSE_DOTS[int(time.time() * 2.5) % 4]
            model = self.session.model or "CRUX"
            now = datetime.now().strftime("%H:%M")

            # Emoji is 2 cells wide, pulse dot is 2 cells wide
            left_vis = 2 + 2 + len(f"CRUX Studio v{_CRUX_VERSION}")  # emoji(2) + spaces(2) + brand
            right_vis = 1 + len(model) + 1 + 2 + 1 + 5  # space + model + space + pulse(2) + space + HH:MM
            pad = max(1, tw - left_vis - right_vis)

            pieces: list[tuple[str, str]] = [
                (bstyle, f" {bicon} "),
                ("class:header-logo", f"CRUX Studio v{_CRUX_VERSION}"),
                ("class:header-sep", "─" * pad),
                ("class:header-model", f" {model} "),
                ("class:header-latency", pulse),
                ("class:status-bar-context", f" {now}"),
            ]
            return FormattedText(pieces)

        header_window = Window(
            content=FormattedTextControl(_header_content),
            height=1,
            style="class:header-bar",
            always_hide_cursor=True,
        )

        # ── Header separator ──
        def _header_sep():
            return FormattedText([("class:header-sep", "╠" + "═" * (_tw() - 2) + "╣")])

        header_sep_window = Window(
            content=FormattedTextControl(_header_sep),
            height=1,
            style="class:header-bar",
            always_hide_cursor=True,
        )

        # ── Thinking Panel (between messages and activity) ──
        def _thinking_content():
            return self.thinking_panel.render(_tw())

        thinking_window = Window(
            content=FormattedTextControl(_thinking_content),
            height=lambda: self.thinking_panel.height(_tw()),
            style="class:message-area",
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        # ── Activity Bar ──
        def _activity_content():
            try:
                count = self._log_count()
                if count == 0:
                    return FormattedText([])
                with self._activity_lock:
                    max_lines = (
                        self._activity_expanded_height if self._activity_expanded else self._activity_collapsed_height
                    )
                    log_snapshot = self._log_snapshot(limit=max_lines)
                tw = _tw()
                if tw <= 0:
                    return FormattedText([])
                pieces: list[tuple[str, str]] = []
                for entry in log_snapshot:
                    if not entry:
                        continue
                    if len(entry) == 3:
                        icon, style_class, msg = entry
                    elif len(entry) == 2:
                        icon, msg = entry; style_class = ""
                    else:
                        continue
                    text = f"{icon} {msg}".replace("\n", " ").replace("\r", " ")[: tw - 4]
                    pieces.append((style_class, text))
                    pieces.append(("", "\n"))
                return FormattedText(pieces)
            except Exception:
                import logging
                logging.getLogger("crux.ui").debug("activity_content render failed", exc_info=True)
                return FormattedText([])
                pieces.append(("", "\n"))
            return FormattedText(pieces)

        activity_window = Window(
            content=FormattedTextControl(_activity_content),
            height=lambda: (
                self._activity_expanded_height if self._activity_expanded else self._activity_collapsed_height
            ) if self._log_count() else 0,
            style="class:message-area",
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        # ── Activity separator ──
        def _activity_sep():
            if self._log_count() == 0:
                return FormattedText([])
            return FormattedText([("class:input-border", "─" * _tw())])

        activity_sep_window = Window(
            content=FormattedTextControl(_activity_sep),
            height=lambda: 1 if self._log_count() else 0,
            style="class:input-border",
            always_hide_cursor=True,
        )

        # ── Input Box ──
        def _input_prompt():
            return f"║ {'*' if self._thinking else '>'} "

        input_ctrl = BufferControl(
            buffer=self.input_buffer,
            input_processors=[BeforeInput(_input_prompt)],
            focusable=True,
        )

        input_window = Window(
            content=input_ctrl,
            height=Dimension(min=1, max=10),
            style="class:input-field",
            dont_extend_height=True,
            wrap_lines=False,
        )

        # ── Input border (bottom of input frame) ──
        def _input_bottom():
            tw = _tw()
            hint = self._build_hint_text()
            hint_vis = 46
            bars_count = max(0, tw - hint_vis - 2)
            bars = "─" * bars_count
            return FormattedText(
                [
                    ("class:input-border", f"╚{bars}"),
                    ("class:welcome-desc", hint),
                    ("class:input-border", "╝"),
                ]
            )

        input_bottom_window = Window(
            content=FormattedTextControl(_input_bottom),
            height=1,
            style="class:input-border",
            always_hide_cursor=True,
        )

        # ── Status Bar ──
        def _status_content():
            return self._build_status()

        status_window = Window(
            content=FormattedTextControl(_status_content),
            height=1,
            style="class:status-bar",
            always_hide_cursor=True,
        )

        # ── Screen overlay ──
        self._screen_window = Window(
            content=FormattedTextControl(self._render_active_screen),
            always_hide_cursor=True,
        )

        # ── Assemble layout (full-screen replacement) ──
        screen_mode = Condition(lambda: self.screen_stack.active)

        normal_body = HSplit(
            [
                header_window,
                header_sep_window,
                self.message_pane.pane,  # Messages + Welcome (weight=1)
                thinking_window,  # Thinking (0-N, conditional)
                activity_sep_window,  # Separator above activity
                activity_window,  # Activity (0-1, conditional)
                input_window,  # Input (1-8)
                input_bottom_window,  # Input frame bottom
                status_window,  # Status (1)
            ],
            style="class:app",
        )

        # ── Focus Mode: full-height message area only (F12) ──
        focus_body = Window(
            content=self.message_pane.pane.content,
            always_hide_cursor=True,
        )
        focus_condition = Condition(lambda: self._focus_mode)
        normal_condition = Condition(lambda: not self._focus_mode and not self.screen_stack.active)

        root = HSplit(
            [
                ConditionalContainer(self._screen_window, filter=screen_mode),
                ConditionalContainer(normal_body, filter=normal_condition),
                ConditionalContainer(focus_body, filter=focus_condition),
            ],
            style="class:app",
        )

        # On Windows with a Unix-like terminal (Git Bash, etc.), create_output()
        # defaults to Win32Output which fails. Force Vt100_Output instead.
        if _sys.platform == "win32" and "TERM" in os.environ:
            output = Vt100_Output.from_pty(_sys.stdout, term=os.environ.get("TERM"))
        else:
            output = create_output()

        return Application(
            layout=Layout(root),
            key_bindings=self.kb,
            style=build_style_v2(self._layout_mgr.theme_mode),
            full_screen=True,
            mouse_support=True,
            output=output,
        )

    # ══════════════════════════════════════════════════════════════
    #  Status bar (enhanced with context bar)
    # ══════════════════════════════════════════════════════════════

    # ── Screen renderer ──

    def _render_active_screen(self):
        """Render currently active screen, or empty if none."""
        screen = self.screen_stack.current
        if screen is None:
            from prompt_toolkit.formatted_text import FormattedText

            return FormattedText([])
        tw = _tw()
        return screen.render(tw)

    def _build_status(self) -> FormattedText:
        tw = _tw()

        # ── Status: dot + model + cwd + git | context bar + latency ──
        # Status dot color: green=idle, yellow=thinking
        status_dot = ("class:status-bar-beast-qilin", "◉") if self._thinking else ("class:status-bar-beast-xuanwu", "●")

        model_str = self.session.model or "CRUX"
        cwd_str = str(Path.cwd())
        home = os.path.expanduser("~")
        if cwd_str.startswith(home):
            cwd_str = "~" + cwd_str[len(home) :]
        git_str = self._cached_git

        # Right section: methodology + context + latency
        right_parts: list[tuple[str, str]] = []
        if _get_methodology_state is not None:
            try:
                ms = _get_methodology_state()
                level_map = {"micro": "A", "normal": "B", "complex": "C", "critical": "D"}
                level = level_map.get(ms.task_level.value, "")
                if level:
                    style_map = {
                        "A": "class:status-bar-level-a",
                        "B": "class:status-bar-level-b",
                        "C": "class:status-bar-level-c",
                        "D": "class:status-bar-level-d",
                    }
                    right_parts.append((style_map.get(level, "class:status-bar"), f"[{level}]"))
            except Exception as e:
                logger.debug("Non-critical: %s", e, exc_info=True)

        bar = context_bar(self._cached_ctx_pct, width=8)
        if self._cached_ctx_pct > 0:
            right_parts.append(("class:status-bar-context", f" {bar} {self._cached_ctx_pct:.0f}%"))

        # ── Provider status ──
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            active = mgr.state.active
            circuit = mgr.state.circuit_state(active)
            if circuit != "CLOSED":
                right_parts.append(("class:status-bar-context", f" ⚡{active}⚠{circuit}"))
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

        # ── Last run summary ──
        try:
            from core.run_summary import list_recent_runs

            runs = list_recent_runs(1)
            if runs:
                r = runs[0]
                status = r.get("status", "?")
                failed = r.get("failed", 0)
                total = r.get("total", 0)
                if status == "done":
                    right_parts.append(("class:status-bar-level-a", f" ✓{total}"))
                elif failed > 0:
                    right_parts.append(("class:status-bar-level-d", f" run:{status} ✗{failed}/{total}"))
                else:
                    right_parts.append(("class:status-bar-level-a", f" run:{status} ✓{total}"))
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

        # ── Provider latency ──
        try:
            from core.provider_history import get_all_stats

            stats = get_all_stats(5)
            latencies = [
                f"{pid}:{s.get('avg_latency_ms', 0):.0f}ms"
                for pid, s in list(stats.items())[:2]
                if s.get("avg_latency_ms")
            ]
            if latencies:
                right_parts.append(("class:status-bar-context", " " + " ".join(latencies)))
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

        if self._latency is not None:
            right_parts.append(("class:status-bar-context", f" ⚡{self._latency:.1f}s"))

        # Assemble
        sd_style, sd_char = status_dot
        pieces: list[tuple[str, str]] = [
            (sd_style, f" {sd_char} "),
            ("class:status-bar-model", model_str),
            ("class:status-bar-path", f"  {cwd_str}"),
        ]
        if git_str:
            pieces.append(("class:status-bar-git", git_str))

        # Padding
        left_visible = 3 + len(model_str) + 2 + len(cwd_str) + len(git_str)
        right_text = " ".join(t for _, t in right_parts)
        pad = max(2, tw - left_visible - len(right_text) - 2)
        pieces.append(("class:status-bar", " " * pad))

        for style, text in right_parts:
            pieces.append((style, text))

        return FormattedText(pieces)

    # ══════════════════════════════════════════════════════════════
    #  Input handling
    # ══════════════════════════════════════════════════════════════

    def _render_dashboard(self):
        """Render dashboard using problem-oriented DashboardState + responsive LayoutConfig."""
        from prompt_toolkit.formatted_text import FormattedText

        layout_config = self._layout_mgr.config

        # Hide dashboard entirely when layout says so
        if not layout_config.dashboard_visible:
            return FormattedText([])

        # Feed current state to dashboard state
        if self._streaming:
            self._dash_state.set_state("streaming")
        elif self._thinking:
            self._dash_state.set_state("thinking")
        # Note: _dash_state stays as-is otherwise (idle/active/error managed externally)

        try:
            from ui.dashboard import render_dashboard

            result = render_dashboard(state=self._dash_state, layout=layout_config)
            return FormattedText(result)
        except Exception as e:
            return FormattedText([("class:header-error", f"Dashboard error: {e}")])

    def _log_append(self, item: tuple[str, str, str]) -> None:
        with self._activity_lock:
            self._activity_log.append(item)
            if len(self._activity_log) > self._activity_log_limit:
                del self._activity_log[: -self._activity_log_limit]

    def _log_update_last(self, item: tuple[str, str, str]) -> None:
        with self._activity_lock:
            if self._activity_log:
                self._activity_log[-1] = item

    def _log_clear(self) -> None:
        with self._activity_lock:
            self._activity_log.clear()

    def _log_snapshot(self, limit: int | None = None) -> list[tuple[str, str, str]]:
        with self._activity_lock:
            if limit is None:
                return list(self._activity_log)
            return list(self._activity_log[-limit:])

    def _log_last(self) -> tuple[str, str, str] | None:
        with self._activity_lock:
            if self._activity_log:
                return self._activity_log[-1]
            return None

    def _log_count(self) -> int:
        with self._activity_lock:
            return len(self._activity_log)

    def _on_accept(self, buf: Buffer) -> bool:
        try:
            text = buf.text
            buf.reset()
            # ── Input sanitization: strip ANSI escapes, null bytes, control chars ──
            text = self._sanitize_input(text)
            if not text:
                return True

            # ── Command routing ──
            if self._handle_command(text):
                return True

            # ── Feed accepted words to completer ──
            words = [w.strip().rstrip(",.;:!?") for w in text.split() if len(w.strip()) >= 3]
            if words:
                self._completer.update_history_words(words)

            # ── Thinking guard — queue input if streaming ──
            if self._thinking or self._streaming:
                self._queue_input_while_streaming(text)
                return True

            # ── Submit for streaming ──
            self._submit_user_message(text)
            return True

        except Exception as e:
            self._log_append(("✗", "class:activity-fail", f"Input failed: {type(e).__name__}: {self._shorten(e, 80)}"))
            with contextlib.suppress(Exception):
                self.message_pane.append_error(f"Input processing failed: {type(e).__name__}: {e}")
            return False

    # ══════════════════════════════════════════════════════════════
    #  Command handlers
    # ══════════════════════════════════════════════════════════════

    def _handle_command(self, text: str) -> bool:
        """Route all command-like inputs. Returns True if handled."""
        # ── Drag-drop image detection ──
        drag_images = detect_drag_images(text)
        if drag_images and len(drag_images) == 1:
            self._send_image(drag_images[0])
            return True
        if drag_images:
            for img in drag_images:
                self._send_image(img)
            return True

        # ── Single image path ──
        single_path = is_image_path(text)
        if single_path:
            self._send_image(single_path)
            return True

        # ── Quit ──
        if text in ("/q", "/quit", "/exit"):
            self._app.exit()
            return True

        # ── Screen commands ──
        if text == "/dashboard" or text.startswith("/dashboard "):
            self._toggle_screen("dashboard")
            return True
        if text == "/incidents" or text.startswith("/incidents "):
            self._toggle_screen("incidents")
            return True
        if text == "/remediate" or text.startswith("/remediate "):
            screen = self._available_screens.get("remediate")
            if text.startswith("/remediate run "):
                iid = text[15:].strip()
                screen.run(iid) if hasattr(screen, "run") else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            elif " " in text:
                cat = text.split(" ", 1)[1]
                screen.select(cat) if hasattr(screen, "select") else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            else:
                screen.back() if hasattr(screen, "back") else None
            self._toggle_screen("remediate")
            self._app.invalidate()
            return True
        if text == "/replay" or text.startswith("/replay "):
            screen = self._available_screens.get("replay")
            if " " in text:
                rid = text.split(" ", 1)[1]
                screen.select(rid) if hasattr(screen, "select") else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            else:
                screen.back() if hasattr(screen, "back") else None
                self._toggle_screen("replay")
            self._app.invalidate()
            return True

        # ── Recent actions ──
        if text == "/recent-actions":
            try:
                from core.remediation_executor import get_recent_actions

                acts = get_recent_actions(15)
                lines = ["Recent Actions:"]
                lines.extend(
                    f"  [{a.get('risk', '?')}] {a.get('command', '?'):40s} {a.get('status', '?')}" for a in acts
                )
                self.message_pane.append_info("\n".join(lines))
            except Exception as e:
                self.message_pane.append_error(f"Error: {e}")
            return True

        # ── Theme switching (per 3-platform debate) ──
        if text.startswith("/theme"):
            from ui.theme_v2 import PALETTES

            parts = text.split()
            if len(parts) >= 2:
                choice = parts[1].strip().lower()
                valid = set(PALETTES.keys()) | {"normal", "high_contrast", "mono"}
                if choice in valid:
                    self._layout_mgr._override_theme = choice
                    self._on_layout_changed(self._layout_mgr.config)
                    if choice in PALETTES:
                        self.message_pane.append_info(
                            f"Theme: {PALETTES[choice]['name']} \u2014 {PALETTES[choice]['desc']}"
                        )
                    else:
                        self.message_pane.append_info(f"Theme mode: {choice}")
                else:
                    themes_list = ", ".join(sorted(PALETTES.keys()))
                    self.message_pane.append_info(
                        f"Theme not found: {choice}. Palettes: {themes_list}. Modes: normal, high_contrast, mono"
                    )
            else:
                current = getattr(self._layout_mgr, "_override_theme", None) or self._layout_mgr.theme_mode
                if current in PALETTES:
                    self.message_pane.append_info(
                        f"Current: {PALETTES[current]['name']} \u2014 {PALETTES[current]['desc']}"
                    )
                else:
                    self.message_pane.append_info(f"Current mode: {current}")
            return True

        # ── System metrics toggle ──
        if text == "/sys":
            self._dash_state.toggle_secondary()
            if self._dash_state._show_secondary:
                self.message_pane.append_info("System metrics: ON (Ctrl+T to hide)")
            else:
                self.message_pane.append_info("System metrics: OFF")
            return True

        # ── Panel commands ──
        if text == "/runs" or text.startswith("/runs "):
            try:
                from core.remediation_executor import get_recent_actions

                limit = 10
                parts = text.split(" ", 1)
                if len(parts) > 1 and parts[1].isdigit():
                    limit = min(50, max(1, int(parts[1])))
                actions = get_recent_actions(limit)
                pieces = render_run_summary(actions, _tw())
                for _style, line in pieces:
                    self.message_pane.append_message("info", line)
            except Exception as e:
                self.message_pane.append_error(f"Runs error: {e}")
            return True

        if text == "/route" or text.startswith("/route "):
            try:
                from core.chat import get_provider_name

                parts = text.split(" ", 1)
                target = parts[1] if len(parts) > 1 else "last"
                route = (
                    {
                        "attempts": [
                            {"provider": get_provider_name(), "model": "...", "status": "success", "latency_ms": 0}
                        ]
                    }
                    if not hasattr(self, "_last_route") or not self._last_route
                    else self._last_route
                )
                pieces = render_provider_route(route, _tw())
                for _style, line in pieces:
                    self.message_pane.append_message("info", line)
            except Exception as e:
                self.message_pane.append_info(f"Provider route: {e}")
            return True

        if text == "/incidents" or text.startswith("/incidents "):
            try:
                parts = text.split(" ", 1)
                status_filter = parts[1].strip() if len(parts) > 1 else None
                if status_filter and status_filter not in {"open", "acknowledged", "closed"}:
                    self.message_pane.append_error("Usage: /incidents [open|acknowledged|closed]")
                    return True
                incidents = load_incidents(status_filter)
                pieces = render_incidents(incidents, _tw(), status_filter)
                for _style, line in pieces:
                    self.message_pane.append_message("info", line)
            except Exception as e:
                self.message_pane.append_error(f"Incidents error: {e}")
            return True

        # ── Download commands ──
        if text == "/download" or text.startswith("/download ") or text == "/downloads":
            from tools.download_tool import handle_download_command

            return handle_download_command(
                text,
                _tw(),
                self.message_pane.append_message,
                self.message_pane.append_error,
                self._log_append,
            )
        # ── Dashboard ──
        if text == "/dashboard":
            try:
                from core.remediation_executor import get_recent_actions

                self._log_clear()
                self.message_pane.append_message("info", " CRUX DASHBOARD\n")
                self.message_pane.append_message("info", " R refresh \u2502 Q/Esc back\n\n")

                actions = get_recent_actions(5)
                for _style, line in render_run_summary(actions, _tw()):
                    self.message_pane.append_message("info", line)
                self.message_pane.append_message("info", "")

                incidents = load_incidents("open")[:5]
                for _style, line in render_incidents(incidents, _tw(), "open"):
                    self.message_pane.append_message("info", line)
            except Exception as e:
                self.message_pane.append_error(f"Dashboard error: {e}")
            return True

        # ── Run detail ──
        if text == "/run" or text.startswith("/run "):
            try:
                from core.remediation_executor import get_recent_actions
                from ui.panels.run_detail_panel import render_run_detail

                parts = text.split(" ", 1)
                target = parts[1].strip() if len(parts) > 1 else "last"
                actions = get_recent_actions(20)
                run = actions[0] if actions and target == "last" else None
                if not run:
                    for a in actions:
                        if target in (a.get("run_id", ""), a.get("incident_id", "")):
                            run = a
                            break
                self._log_clear()
                if run:
                    for _s, line in render_run_detail(run, _tw()):
                        self.message_pane.append_message("info", line)
                else:
                    self.message_pane.append_info(f"No run found: {target}")
            except Exception as e:
                self.message_pane.append_error(f"Run error: {e}")
            return True

        # ── Incident detail ──
        if text == "/incident" or text.startswith("/incident "):
            try:
                from ui.panels.incident_detail_panel import render_incident_detail

                parts = text.split(" ", 1)
                target = parts[1].strip() if len(parts) > 1 else "last"
                incidents = load_incidents()
                inc = incidents[0] if incidents and target == "last" else None
                if not inc:
                    for i in incidents:
                        if i.get("id") == target:
                            inc = i
                            break
                self._log_clear()
                if inc:
                    for _s, line in render_incident_detail(inc, _tw()):
                        self.message_pane.append_message("info", line)
                else:
                    self.message_pane.append_info(f"No incident found: {target}")
            except Exception as e:
                self.message_pane.append_error(f"Incident error: {e}")
            return True

        # ── Copy command ──
        if text.startswith("/copy"):
            ok, msg = self._copy_mgr.handle_command(text)
            icon, style = ("✓", "class:activity-done") if ok else ("✗", "class:activity-fail")
            self._log_append((icon, style, msg[:120]))
            return True

        # ── Provider health ──
        if text == "/providers":
            try:
                from core.remediation_executor import get_recent_actions
                from ui.panels.system_status_panel import render_system_status

                providers = []
                seen = set()
                for a in get_recent_actions(15):
                    chain = a.get("provider_chain", []) or []
                    for prov in chain:
                        if prov not in seen:
                            seen.add(prov)
                            providers.append(
                                {
                                    "provider": prov,
                                    "health_score": 1.0,
                                    "circuit_state": "CLOSED",
                                    "latency_ema_ms": 0,
                                    "status": "ok",
                                }
                            )
                if not providers:
                    providers = [
                        {
                            "provider": "deepseek-v4-flash",
                            "health_score": 1.0,
                            "circuit_state": "CLOSED",
                            "latency_ema_ms": 0,
                            "status": "ok",
                        }
                    ]
                self._log_clear()
                for _s, line in render_system_status(providers, _tw()):
                    self.message_pane.append_message("info", line)
            except Exception as e:
                self.message_pane.append_error(f"Providers error: {e}")
            return True

        # ── Slash commands ──
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

        return False

    def _submit_user_message(self, text: str) -> None:
        """Submit user input via Control Plane (pending window / Ctrl+Z undo)."""
        text = (text or "").strip()
        if not text:
            return

        self.message_pane.append_message("user", text)
        self._msg_store.append("user", text)
        self._sync_copy_mgr()

        with self._state_lock:
            is_streaming = getattr(self, "_streaming", False)

        if is_streaming:
            # 执行中 → 优先插话
            control().priority_message(text)
            self._log_append(("→", "class:activity-info", f"优先插话: {self._shorten(text, 60)}"))
            self._queue_input_while_streaming(text)
            return

        # 空闲 → pending 窗口
        msg = control().send_message(text)
        self._pending_msg_id = msg.id
        self._pending_text = text
        self._log_append(
            (
                "→",
                "class:activity-info",
                f"待发送 ({control().outbox.UNDO_WINDOW_MS // 1000}s 可撤销): {self._shorten(text, 30)}",
            )
        )
        self._start_pending_commit_timer()

    def _sync_copy_mgr(self) -> None:
        """Sync CopyManager from MessageStore (reads directly, kept as no-op shim)."""
        if hasattr(self, "_copy_mgr") and hasattr(self, "_msg_store"):
            self._copy_mgr.sync_store(self._msg_store)

    def _start_pending_commit_timer(self) -> None:
        """Pending 窗口过期后自动提交。"""

        # Guard: cancel any existing timer to prevent duplicate worker threads
        _prev_timer = getattr(self, "_pending_timer", None)
        if _prev_timer is not None and _prev_timer.is_alive():
            try:
                # Mark old timer as cancelled so it becomes a no-op
                self._pending_cancelled = True
            except Exception:
                pass

        self._pending_cancelled = False

        def wait_and_commit():
            time.sleep(control().outbox.UNDO_WINDOW_MS / 1000 + 0.1)
            # Check if this timer was cancelled (user sent another message)
            if getattr(self, "_pending_cancelled", False):
                return
            pending = control().outbox.get_pending()
            if not pending:
                return
            msg = pending[0]
            control().outbox.commit(msg.id)
            self._log_append(("→", "class:activity-info", f"消息已发送: {self._shorten(msg.text, 30)}"))
            with self._state_lock:
                self._thinking = True
                self._streaming = True
                self._anim_gov.streaming = True
                emit_state(streaming=True, thinking=self._thinking)
                self._dash_state.set_state("streaming")
            from threading import Thread as _Thread

            self._worker_thread = _Thread(
                target=self._stream_response,
                args=(msg.text,),
                daemon=True,
                name="stream-response",
            )
            self._worker_thread.start()

        self._pending_timer = threading.Thread(target=wait_and_commit, daemon=True, name="pending-commit")
        self._pending_timer.start()

    def _undo_pending(self) -> bool:
        """Ctrl+Z 撤销 pending 消息。"""
        if not self._pending_msg_id:
            return False
        if control().retract(self._pending_msg_id):
            self._log_append(("→", "class:activity-warn", "消息已撤销"))
            self.message_pane.pop_last_message()
            self._ui(self.message_pane._auto_scroll)
            self._pending_msg_id = None
            self._pending_text = ""
            return True
        return False

    def _cancel_current_response(self) -> None:
        """Cancel the currently streaming response (via Control Plane)."""
        control().cancel_run("用户取消响应")
        with self._state_lock:
            self._cancel_requested = True
        with contextlib.suppress(Exception):
            self._spinner.stop()
        self._ui(self.message_pane.stream_end, _force=True)
        self._log_append(("→", "class:activity-warn", "响应已取消"))

    def _queue_input_while_streaming(self, text: str) -> None:
        """Queue user input during streaming — via priority message."""
        text = text.strip()
        if not text:
            return

        # 发送优先插话控制事件
        control().priority_message(text)
        self._log_append(("→", "class:activity-info", f"执行中插话已入队: {self._shorten(text, 60)}"))

        with self._state_lock:
            self._queued_text = text

        self._log_append(("→", "class:activity-info", f"Queued: {self._shorten(text, 60)}"))

    def _get_queued_input(self) -> str:
        """Get queued input and clear."""
        with self._state_lock:
            t = self._queued_text
            self._queued_text = ""
            self._clear_queued_input = True
        return t

    def _clear_queued_input_flag(self) -> None:
        """Clear queued input flag."""
        with self._state_lock:
            self._queued_text = ""
            self._clear_queued_input = True

    def _build_hint_text(self) -> str:
        with self._state_lock:
            streaming = self._streaming or self._thinking
        if streaming:
            return " 正在响应：Enter 暂存输入 │ Ctrl+C 中断 "

        if getattr(self, "_activity_expanded", False):
            return ""

        return ""

    def _send_image(self, image_path: str) -> None:
        if self._thinking:
            self.message_pane.append_info("Please wait — still processing previous request")
            return
        with self._state_lock:
            self._thinking = True
        self.thinking_panel.clear()
        fname = os.path.basename(image_path)
        self.message_pane.append_message("user", f"[图片: {fname}]")
        self._streaming = True
        self._spinner.start()
        self._refresh_status()
        self._executor.submit(self._stream_image_response, image_path)

    # ══════════════════════════════════════════════════════════════
    #  Streaming
    # ══════════════════════════════════════════════════════════════

    def _stream_image_response(self, image_path: str) -> None:
        try:
            prompt = "请详细描述这张图片的内容。如果是截图，请描述界面、文字和关键信息。"
            self._ui(self.message_pane.stream_start, "crux")
            self._log_append(("●", "class:message-tool", f"视觉分析: {os.path.basename(image_path)}"))
            for kind, payload in self.session.send_stream(prompt, image_url=image_path):
                if kind == "text":
                    self._ui(self.message_pane.stream_append, str(payload))
                elif kind == "thinking":
                    self.thinking_panel.append(str(payload))
                elif kind == "info":
                    self._ui(self.message_pane.append_info, str(payload))
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
            _last_entry = self._log_last()
            if _last_entry:
                last_icon, _, last_msg = _last_entry
                if "●" in last_icon:
                    self._log_update_last(
                        ("✓", "class:activity-done", last_msg.replace("视觉分析: ", "视觉分析完成: "))
                    )
            self._ui(self.message_pane.stream_end, _force=True)
        except Exception as e:
            self._ui(self.message_pane.append_error, f"图片分析失败: {e}", _force=True)
            self._log_append(("✗", "class:activity-fail", f"视觉分析失败: {self._error_summary(e)}"))
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            with self._state_lock:
                self._streaming = False
                self._thinking = False
                self._anim_gov.streaming = False
                self._dash_state.set_state("idle")
            emit_state(streaming=False, thinking=False)
            self._spinner.stop()
            self._ui(self._refresh_status, _force=True)

    def _stream_response(self, user_text: str) -> None:
        # Stream inactivity timeout: fire only after 120s with NO events
        _last_event = time.monotonic()
        _timeout_triggered = False

        def _timeout_guard():
            nonlocal _timeout_triggered
            while True:
                time.sleep(5)
                idle = time.monotonic() - _last_event
                if idle > 120 and not _timeout_triggered:
                    _timeout_triggered = True
                    try:
                        self._log_append(("⏱", "class:activity-warn", f"Stream 超时 ({idle:.0f}s 无响应)"))
                    except Exception:
                        pass
                    return

        _timeout_thread = threading.Thread(target=_timeout_guard, daemon=True)
        _timeout_thread.start()
        try:
            self._ui(self.message_pane.stream_start, "crux")
            pending_tool = None
            _tool_seq = 0  # running tool counter
            _t0 = time.monotonic()
            _first_token = False
            for kind, payload in self.session.send_stream(user_text):
                _last_event = time.monotonic()  # reset inactivity timer
                if not _first_token and kind in ("text", "thinking"):
                    _first_token = True
                    self._latency = time.monotonic() - _t0  # ── 检查优先插话标记（工具边界已设置） ──
                _interrupted_flag = False
                with self._state_lock:
                    _interrupted_flag = getattr(self, "_interrupted_by_priority", False)
                if _interrupted_flag:
                    break
                if kind == "text":
                    self._ui(self.message_pane.stream_append, str(payload))
                elif kind == "thinking":
                    self.thinking_panel.append(str(payload))
                    self._ui(lambda: None)
                elif kind == "info":
                    msg = str(payload).strip()
                    if not msg:
                        continue
                    if msg.startswith("正在执行 "):
                        tool_name = msg[5:].rstrip(".")
                        _tool_seq += 1
                        pending_tool = tool_name
                        self._log_append(("●", "class:activity-running", f"#{_tool_seq} {tool_name}"))
                    elif msg.startswith("正在生成"):
                        action = msg[2:].rstrip(".")
                        pending_tool = action
                        self._log_append(("●", "class:activity-running", f"生成 {action}"))
                    elif "执行完成" in msg:
                        if pending_tool:
                            _last_entry = self._log_last()
                            if _last_entry:
                                last_icon, _, last_msg = _last_entry
                                if "●" in last_icon:
                                    self._log_update_last(
                                        (
                                            "✓",
                                            "class:activity-done",
                                            last_msg.replace("执行 ", "").replace("生成 ", ""),
                                        )
                                    )
                        pending_tool = None
                    elif "fallback" in msg.lower() or "连接中断" in msg:
                        self._log_append(("⚠", "class:activity-warn", msg[:100]))
                    elif "预算" in msg:
                        self._log_append(("💰", "class:activity-info", msg[:100]))
                    else:
                        # Show uncategorized info messages (provider switches, pipeline results, etc.)
                        _folded = len(msg) > 300
                        if _folded:
                            preview = msg[:280] + f"\n... [折叠 {len(msg)} 字符]"
                            self._ui(self.message_pane.append_info, preview)
                        else:
                            self._ui(self.message_pane.append_info, msg)
                        self._log_append(("·", "class:activity-info", msg[:120]))
                    self._ui(lambda: None)
                elif kind == "tool_result":
                    if pending_tool:
                        _last_entry = self._log_last()
                        if _last_entry:
                            last_icon, _, last_msg = _last_entry
                            if "●" in last_icon:
                                self._log_update_last(
                                    (
                                        "✓",
                                        "class:activity-done",
                                        last_msg.replace("执行 ", "").replace("生成 ", ""),
                                    )
                                )
                    pending_tool = None
                    self._ui(lambda: None)

                    # ── 工具边界：检查优先插话 ──
                    if control().queue.has_events():
                        _ev = control().queue.peek()
                        if _ev and _ev.type == ControlEventType.PRIORITY_MESSAGE:
                            self._log_append(("⚡", "class:activity-warn", "检测到优先插话，将在当前工具完成后处理"))
                            # 标记中断，在循环结束后处理
                            with self._state_lock:
                                self._interrupted_by_priority = True
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
                    self._log_append(("✗", "class:activity-fail", str(payload)[:120]))
                elif kind in ("image", "video"):
                    d = payload if isinstance(payload, dict) else {}
                    loc = d.get("local_path", "") or d.get("url", "") or d.get("video_url", "")
                    if loc:
                        self._ui(self.message_pane.append_info, f"Saved: {loc}")
                        self._log_append(("✓", "class:activity-done", f"已保存: {loc}"))
                else:
                    # ── Status-line events: 路由到状态栏或通知区 ──
                    status_kinds = {
                        "status_update", "watchdog_alert", "watchdog_warning",
                        "system_warning", "system_error", "provider_fallback",
                        "notice", "connection_error", "system_info",
                        "tool_failed", "tool_started", "tool_finished", "tool_progress",
                    }
                    if kind in status_kinds:
                        text = str(payload)[:120]
                        if "error" in kind or "failed" in kind or "alert" in kind:
                            self._ui(self.message_pane.append_error, text)
                        else:
                            self._ui(self.message_pane.append_info, text)
                    else:
                        logger.debug("tui.stream: unhandled kind=%s", kind)
            # Mark any remaining pending tool as done
            if pending_tool:
                _last_entry = self._log_last()
                if _last_entry:
                    last_icon, _, last_msg = _last_entry
                    if "●" in last_icon:
                        self._log_update_last(
                            ("✓", "class:activity-done", last_msg.replace("执行 ", "").replace("生成 ", ""))
                        )
            self._ui(self.message_pane.stream_end, _force=True)
        except Exception as e:
            _err_name = type(e).__name__
            _err_msg = str(e)
            # ── Error classification with recovery hints ──
            _hint = ""
            _is_critical = False
            if "Connection" in _err_name or "ConnectError" in _err_name or "connect" in _err_msg.lower():
                _hint = "网络连接失败 — 检查网络后重试，或切换供应商 /provider"
            elif "Timeout" in _err_name or "timeout" in _err_msg.lower() or "timed out" in _err_msg.lower():
                _hint = "请求超时 — 模型响应慢，可简化问题后重试"
            elif "RateLimit" in _err_name or "429" in _err_msg or "rate" in _err_msg.lower():
                _hint = "频率限制 — 请等待 30 秒后重试"
            elif "Authentication" in _err_name or "401" in _err_msg or "403" in _err_msg or "key" in _err_msg.lower():
                _hint = "认证失败 — 检查 API Key 配置"
                _is_critical = True
            elif "Memory" in _err_name or "context" in _err_msg.lower() or "token" in _err_msg.lower():
                _hint = "上下文过长 — 已自动压缩，请重试或将任务拆分"
            elif "json" in _err_msg.lower() or "JSONDecode" in _err_name:
                _hint = "数据格式错误 — 可能是模型输出异常，请重试"
            else:
                _hint = "未知错误 — 请重试，如持续出现请查看日志"
            _icon = "✗" if not _is_critical else "☠"
            self._log_append((_icon, "class:activity-fail", f"{_err_name}: {_hint}"))
            self._ui(self.message_pane.append_error, f"{_err_name}: {self._shorten(_err_msg, 200)}\n→ {_hint}", _force=True)
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            with self._state_lock:
                self._streaming = False
                self._thinking = False
            self.thinking_panel.done()
            self._spinner.stop()
            self._ui(self._refresh_status, _force=True)
            # ── Turn summary: tools × elapsed × latency ──
            try:
                _elapsed = time.monotonic() - _t0
            except (NameError, UnboundLocalError):
                _elapsed = 0
            _latency = getattr(self, '_latency', 0)
            _score = getattr(self, '_last_agent_score', 0)
            _summary_parts = [f"⏱ {_elapsed:.1f}s"]
            if _tool_seq > 0:
                _summary_parts.append(f"🔧 {_tool_seq} tools")
            if _latency > 0:
                _summary_parts.append(f"⚡ {_latency:.1f}s first token")
            if _score >= 5:
                _summary_parts.append(f"🧠 agent score {_score:.0f}")
            self._log_append(("", "class:dim", " · ".join(_summary_parts)))
            # Auto-submit queued input or process priority interrupt
            _qt = None
            with self._state_lock:
                _interrupted = self._interrupted_by_priority
                self._interrupted_by_priority = False
                if not _interrupted:
                    _qt = self._queued_text
                    self._queued_text = None

            if _interrupted:
                # 优先插话中断 — 立即处理用户的优先消息
                _ev = control().queue.poll()
                if _ev and _ev.type == ControlEventType.PRIORITY_MESSAGE:
                    _interrupt_text = _ev.payload.get("text", "")
                    if _interrupt_text:
                        self._log_append(
                            ("⚡", "class:activity-warn", f"处理优先插话: {self._shorten(_interrupt_text, 60)}")
                        )
                        # 清除 _queued_text 避免重复提交
                        with self._state_lock:
                            self._queued_text = None
                        from threading import Thread as _T

                        _T(
                            target=self._stream_response, args=(_interrupt_text,), daemon=True, name="priority-stream"
                        ).start()
                        _qt = None
            elif _qt:
                self._log_append(("↪", "class:activity-info", f"自动发送暂存输入: {self._shorten(_qt, 48)}"))
                self._submit_user_message(_qt)
        if self.wire:
            try:
                self.wire.record_turn("assistant", "[streamed]")
            except Exception:
                logger.debug("wire.record_turn failed", exc_info=True)

    # ══════════════════════════════════════════════════════════════
    #  UI helpers
    # ══════════════════════════════════════════════════════════════

    def _ui(self, fn, *a, _force: bool = False):
        try:
            from core.watchdog import Watchdog
            Watchdog.beat("TUI")
        except Exception:
            pass
        try:
            if a:
                fn(*a)
            else:
                fn()
        except Exception:
            logger.warning("TUI _ui callback failed", exc_info=True)
        try:
            app = getattr(self, "_app", None)
            if app is not None and app.is_running:
                now = time.monotonic()
                last = getattr(self, "_last_invalidate", 0.0)
                thinking = getattr(self, "_thinking", False)
                if _force or not thinking or now - last > 0.030:
                    self._last_invalidate = now
                    app.invalidate()
        except Exception:
            if not getattr(self, "_invalidate_failed_once", False):
                self._invalidate_failed_once = True
            logger.warning("TUI _ui invalidate failed", exc_info=True)

    def _toggle_screen(self, name):
        screen = self._available_screens.get(name)
        if not screen:
            return
        # Inject live state into DashboardScreen before render
        if name == "dashboard" and hasattr(screen, "_dash_state_ref"):
            screen._dash_state_ref = getattr(self, "_dash_state", None)
            screen._layout_mgr_ref = getattr(self, "_layout_mgr", None)
        if self.screen_stack.active and self.screen_stack.current.name == name:
            self.screen_stack.pop(self)
        else:
            self.screen_stack.push(screen, self)
        self._app.invalidate()

    def _on_spinner_tick(self) -> None:
        """Called by Spinner thread every ~80ms. Triggers activity bar repaint."""
        if self._log_count() and self._app and self._app.is_running:
            with contextlib.suppress(Exception):
                self._app.invalidate()

    def _on_download_update(self, job) -> None:
        """Called by DownloadManager when a download job changes state."""
        self._log_append(("↓", "class:activity-info", job.summary()[:80]))
        with contextlib.suppress(Exception):
            self._app.invalidate()

    # ── Text utilities ──

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Strip ANSI escape sequences, null bytes, and other dangerous control chars.

        Engineer error messages (compiler output, tracebacks, build logs) frequently
        contain terminal escape codes that corrupt prompt_toolkit rendering and crash
        the TUI. This is a safety gate at the input boundary.
        """
        import re

        # Strip ANSI escape sequences (CSI, OSC, etc.)
        text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
        text = re.sub(r"\x1b\].*?\x07", "", text)  # OSC sequences
        # Strip null bytes — crash json.dumps and various string operations
        text = text.replace("\x00", "")
        # Strip bell and other dangerous single-byte controls
        text = text.replace("\x07", "")
        # Strip leading/trailing whitespace AFTER sanitization
        return text.strip()

    @staticmethod
    def _shorten(text: object, limit: int = 60) -> str:
        value = str(text).replace("\n", " ").replace("\r", " ")
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)] + "…"

    def _error_summary(self, error: Exception, limit: int = 80) -> str:
        name = type(error).__name__
        message = self._shorten(str(error), limit)
        return f"{name}: {message}" if message else name

    def _on_layout_changed(self, new_config):
        """React to layout/environment changes: update theme, invalidate UI."""
        self._current_layout = new_config
        # Apply theme mode
        mode = self._layout_mgr.theme_mode
        try:
            from ui.theme_v2 import build_style_v2

            if self._app is not None:
                self._app.style = build_style_v2(mode)
                self._app.invalidate()
        except Exception as _exc:
            logger.warning("Theme switch failed: %s", _exc, exc_info=True)
            self.message_pane.append_error(f"Theme apply failed: {_exc}")

    def _refresh_status(self):
        self.status_bar.set_model(self.session.model)
        self.status_bar.set_thinking(self._thinking)
        # Cache context percentage
        try:
            chars = sum(len(str(m.get("content", ""))) for m in self.session.messages)
            self._cached_ctx_pct = min(100.0, chars * 0.4 / 128000 * 100)
            self.status_bar.set_context(int(chars * 0.4), 128000)
            # Feed context to dashboard state (per debate: P0 metric)
            self._dash_state._context_pct = self._cached_ctx_pct
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)
        # ── Collect system metrics for secondary panel ──
        if self._dash_state._show_secondary:
            try:
                import psutil

                self._dash_state._cpu_pct = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                self._dash_state._memory_pct = mem.percent
                self._dash_state._memory_used_mb = mem.used // (1024 * 1024)
                self._dash_state._memory_total_mb = mem.total // (1024 * 1024)
                self._dash_state._disk_pct = psutil.disk_usage("/").percent
                self._dash_state._process_count = len(psutil.pids())
                self._dash_state._uptime_hours = 0.0
            except ImportError:
                pass
            except Exception as e:
                logger.debug("Non-critical: %s", e, exc_info=True)

        # Cache git info (call once, not per frame)
        self.status_bar.refresh()
        try:
            b = self.status_bar._branch
            d = self.status_bar._diff_stats
            self._cached_git = f" {b}" + (f" [{d}]" if d else "") if b else ""
        except Exception:
            self._cached_git = ""
        # ── Broadcast state to protocol bus ──
        emit_state(
            model=self.session.model,
            thinking=self._thinking,
            streaming=self._streaming,
            context_pct=self._cached_ctx_pct,
            active_agents=len(getattr(self, "_running_runs", [])),
        )

    def _request_exit(self) -> None:
        """Graceful shutdown request: stop streaming, spinner, thinking."""
        with self._state_lock:
            self._closing = True
            self._cancel_requested = True
            self._streaming = False
            self._thinking = False

        with contextlib.suppress(Exception):
            self._spinner.stop()

        with contextlib.suppress(Exception):
            self.thinking_panel.done()

        with contextlib.suppress(Exception):
            self._log_append(("•", "class:activity-info", "Exiting CRUX..."))

    def _shutdown_resources(self) -> None:
        """Release external resources (spinner, executor, browser bridges).
        Idempotent — double call is safe (signal + atexit + finally).
        """
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True

        with self._state_lock:
            self._closing = True
            self._cancel_requested = True
            self._streaming = False
            self._thinking = False

        with contextlib.suppress(Exception):
            self._spinner.stop()

        with contextlib.suppress(Exception):
            self.thinking_panel.done()

        # Shut down browser / playwright bridges gracefully
        for attr in (
            "_browser_bridge",
            "browser_bridge",
            "_playwright_bridge",
            "playwright_bridge",
            "_browser",
            "browser",
            "_playwright",
            "playwright",
        ):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                if hasattr(obj, "close"):
                    obj.close()
                elif hasattr(obj, "stop"):
                    obj.stop()
                elif hasattr(obj, "shutdown"):
                    obj.shutdown()
            except (BrokenPipeError, EOFError, OSError):
                pass
            except Exception as e:
                logger.debug("Non-critical: %s", e, exc_info=True)

        with contextlib.suppress(Exception):
            self._executor.shutdown(wait=False)

    def run(self):
        # ── signal handlers for graceful Ctrl+C / kill ──
        import atexit as _atexit
        import signal as _signal

        _shutdown_once = False

        def _signal_handler(sig, frame):
            nonlocal _shutdown_once
            if not _shutdown_once:
                _shutdown_once = True
                self._request_exit()
                self._shutdown_resources()
            _sys.exit(0)

        _signal.signal(_signal.SIGINT, _signal_handler)
        if hasattr(_signal, "SIGTERM"):
            _signal.signal(_signal.SIGTERM, _signal_handler)
        _atexit.register(self._shutdown_resources)

        # Populate initial git/latency/context data before first render
        self._refresh_status()
        # Start a lightweight animation timer (~10 fps) for beast icon rotation
        # and live model-name updates. Independent of the activity spinner.
        self._anim_running = True

        def _anim_loop():
            while self._anim_running:
                time.sleep(0.1)
                if self._app and self._app.is_running:
                    with contextlib.suppress(Exception):
                        self._app.invalidate()

        threading.Thread(target=_anim_loop, daemon=True).start()

        try:
            # P0: 启动心跳定时器
            from core.watchdog import Watchdog
            def _heartbeat_tick():
                Watchdog.beat("IDLE")
                self._app.invalidate()
                self._heartbeat_timer = threading.Timer(2.0, _heartbeat_tick)
                self._heartbeat_timer.daemon = True
                self._heartbeat_timer.start()
            _heartbeat_tick()
            self._app.run()
        except KeyboardInterrupt:
            self._request_exit()
        except Exception as e:
            # Crash recovery: don't just die — log the error and try to show it
            logger.exception("TUI app.run() crashed: %s", e)
            try:
                sys.stderr.write(f"\n[CRUX TUI crashed: {type(e).__name__}: {e}]\n")
                sys.stderr.write("The launcher will restart the TUI automatically.\n")
                sys.stderr.flush()
            except Exception:
                pass
            traceback.print_exc(file=sys.stderr)
        finally:
            self._anim_running = False
            self._shutdown_resources()
            # Unregister atexit to avoid double-call on clean exit
            with contextlib.suppress(Exception):
                _atexit.unregister(self._shutdown_resources)
