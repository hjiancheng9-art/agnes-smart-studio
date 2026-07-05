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
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output

# ── Static imports (avoid per-frame re-import) ──
from core.version import __version__ as _CRUX_VERSION
from ui.clipboard_image import detect_drag_images, get_clipboard_image, is_image_path
from ui.message_pane import MessagePane
from ui.status_bar import StatusBar
from ui.theme_v2 import build_style_v2
from ui.dashboard import render_dashboard
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

    def render(self, tw: int): return []
    def on_enter(self, app): pass
    def on_exit(self, app): pass
    def handle_key(self, key: str) -> bool: return False


class ScreenStack:
    """Manages navigation between screens."""
    def __init__(self):
        self._stack = []
    @property
    def current(self): return self._stack[-1] if self._stack else None
    @property
    def active(self): return len(self._stack) > 0
    def push(self, screen, app):
        self._stack.append(screen)
        if app is not None:
            screen.on_enter(app)
    def pop(self, app):
        if not self._stack: return None
        s = self._stack.pop()
        if app is not None: s.on_exit(app)
        return s
    def pop_all(self, app):
        while self._stack: self.pop(app)


class DashboardScreen(Screen):
    name = "dashboard"
    def __init__(self):
        self._cached_data = {}
        self._last_refresh = 0
    def on_enter(self, app):
        self._refresh_data()
        if app: app._app.invalidate()
    def _refresh_data(self):
        import time
        if time.monotonic() - self._last_refresh < 2:
            return
        self._last_refresh = time.monotonic()
        try:
            from core.incident_store import get_incident_trends, load_incidents
            self._cached_data["trends"] = get_incident_trends()
            self._cached_data["incidents"] = load_incidents(limit=10)
        except: pass
        try:
            from core.run_replay import list_replays
            self._cached_data["runs"] = list_replays(limit=5)
        except: pass
    def render(self, tw):
        self._refresh_data()
        d = self._cached_data
        ft = []
        ft.append(("bold", f"{{'═'*tw}}\\n"))
        ft.append(("bold class:header", "  DASHBOARD\\n\\n"))
        trends = d.get("trends", {})
        ft.append(("", f"  Incidents 24h: {trends.get('total', 0)}\\n"))
        incs = d.get("incidents", [])
        for inc in incs[:5]:
            cat = inc.get("category", "?")
            sev = inc.get("severity", "?")
            ft.append(("", f"    [{sev}] {cat}\\n"))
        ft.append(("class:dim", "\\n  /dashboard  /incidents  /remediate  /replay\\n"))
        return ft


class IncidentLogScreen(Screen):
    name = "incidents"
    def __init__(self):
        self._incidents = []
    def on_enter(self, app):
        try:
            from core.incident_store import load_incidents
            self._incidents = load_incidents(limit=50)
        except: self._incidents = []
    def render(self, tw):
        ft = []
        ft.append(("bold", f"{{'═'*tw}}\\n"))
        ft.append(("bold class:header", "  INCIDENT LOG\\n"))
        ft.append(("class:dim", "                      类别         严重度    时间\\n"))
        for i in self._incidents[:20]:
            iid = i.get("incident_id", "?")[:14]
            cat = i.get("category", "?")[:16]
            sev = i.get("severity", "?")
            ts = str(i.get("timestamp", "?"))[:16]
            ft.append(("", f"  {iid}  {cat}  {sev}  {ts}\\n"))
        ft.append(("class:dim", "\\n  Esc: back\\n"))
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
        except: self._cats = []
        self._results = []
    def select(self, cat):
        try:
            from core.incident_playbook import get_playbook
            self._pb = get_playbook(cat)
        except: self._pb = None
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
        ft.append(("bold", f"{{'═'*tw}}\\n"))
        if self._results:
            ft.append(("bold class:header", "  REMEDIATION RESULTS\\n"))
            for r in self._results:
                ic = "\u2713" if r["status"] == "success" else "\u2299" if r["status"] == "pending_approval" else "\u2717"
                ft.append(("", f"    {ic} {r.get('command','?')}: {r['status']}\\n"))
            return ft
        if self._pb:
            ft.append(("bold class:header", f"  {self._pb.get('title', '?')}\\n"))
            ft.append(("class:dim", f"  severity: {self._pb.get('severity', '?')}\\n\\n"))
            for i, s in enumerate(self._pb.get("steps", []), 1):
                ft.append(("", f"    {i}. {s}\\n"))
            auto = self._pb.get("auto_commands", [])
            if auto:
                ft.append(("bold", "\\n  Auto-fix:\\n"))
                for c in auto:
                    ft.append(("", f"    $ {c}\\n"))
        else:
            ft.append(("bold class:header", "  PLAYBOOKS\\n"))
            for c in self._cats:
                ft.append(("", f"    {c}\\n"))
        ft.append(("class:dim", "\\n  /remediate <cat>  /remediate run <id>\\n"))
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
        except: self._records = []
    def select(self, rid):
        try:
            from core.run_replay import load_replay
            self._selected = load_replay(rid)
        except: self._selected = None
    def back(self):
        self._selected = None
    def render(self, tw):
        ft = []
        ft.append(("bold", f"{{'═'*tw}}\\n"))
        ft.append(("bold class:header", "  RUN REPLAYS\\n"))
        ft.append(("class:dim", "  root_trace_id          model          status\\n"))
        for r in self._records[:20]:
            rid = r.get("root_trace_id", "?")[:20]
            st = r.get("status", "?") if hasattr(r, 'get') else "?"
            ft.append(("", f"  {rid}  {st}\\n"))
        ft.append(("class:dim", "\\n  Esc: back\\n"))
        return ft


class ApprovalScreen(Screen):
    name = "approval"
    def __init__(self):
        self._pending = []
    def on_enter(self, app):
        try:
            from ui.tui_v2 import _APPROVAL_PENDING
            self._pending = list(_APPROVAL_PENDING)
        except: pass
    def render(self, tw):
        ft = []
        ft.append(("bold", f"{{'═'*tw}}\\n"))
        ft.append(("bold class:header", "  PENDING APPROVALS\\n"))
        if not self._pending:
            ft.append(("class:dim", "  (none)\\n"))
        else:
            for item in self._pending:
                if item.get("status") == "pending":
                    ft.append(("class:status-warn", f"  [{item.get('risk','?')}] {item.get('command','?')}\\n"))
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
        self._last_invalidate = 0.0
        self._latency: float | None = None
        self._state_lock = threading.Lock()

        # ── Cached values (updated in _refresh_status, read by render) ──
        self._cached_git = ""
        self._cached_ctx_pct = 0.0
        self._show_dashboard = False

        # ── Core components ──
        self.message_pane = MessagePane()
        self.status_bar = StatusBar(model=session.model, cwd=Path.cwd())
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

        # ── Spinner ──
        self._spinner = Spinner(on_tick=self._on_spinner_tick)

        # ── Animation timer (independent of spinner, always running) ──
        self._anim_running = False

        # ── Dashboard mode ──
        self._dashboard_mode = False
        self._normal_container = None   # set in _make_app after building root

        # ── Welcome screen ──
        self._setup_welcome()

        # ── Input ──
        self._history = InMemoryHistory()
        self.input_buffer = Buffer(
            multiline=True,
            accept_handler=self._on_accept,
            history=self._history,
        )

        # ── Key bindings ──
        self.kb = self._setup_keybindings()

        # ── Build app ──
        self._app = self._make_app()

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
                capture_output=True, text=True, timeout=2,
            )
            branch = r.stdout.strip()
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

        def _welcome_renderer() -> FormattedText:
            return build_welcome_formatted(
                model_name=model_name,
                cwd=cwd,
                branch=branch,
            )

        self.message_pane.set_empty_renderer(_welcome_renderer)

    # ══════════════════════════════════════════════════════════════
    #  Key bindings
    # ══════════════════════════════════════════════════════════════

    def _setup_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("escape", "c-m")  # Alt+Enter: insert newline
        @kb.add("c-j")            # Ctrl+J: insert newline (alternative)
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
            self._activity_log.clear()
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

        @kb.add("f11")
        def _(event):
            renderer = event.app.renderer
            renderer.full_screen = not renderer.full_screen
            if not renderer.full_screen and renderer._in_alternate_screen:
                renderer.output.quit_alternate_screen()
                renderer._in_alternate_screen = False
            event.app.renderer.reset(
                leave_alternate_screen=not renderer.full_screen
            )
            event.app.invalidate()

        @kb.add("pageup")
        def _(event):
            self.message_pane.scroll_page_up()
            event.app.invalidate()

        @kb.add("pagedown")
        def _(event):
            self.message_pane.scroll_page_down()
            event.app.invalidate()

        # Note: plain Home/End are consumed by the multiline Buffer for cursor
        # movement. Use Ctrl+Home / Ctrl+End to jump to top/bottom instead.

        @kb.add("c-home")
        def _(event):
            self.message_pane.scroll_to_top()
            event.app.invalidate()

        @kb.add("c-end")
        def _(event):
            self.message_pane.scroll_to_bottom()
            event.app.invalidate()

        @kb.add(Keys.ScrollUp)
        def _(event):
            self.message_pane.scroll_up(5)
            event.app.invalidate()

        @kb.add(Keys.ScrollDown)
        def _(event):
            self.message_pane.scroll_down(5)
            event.app.invalidate()

        return kb

    # ══════════════════════════════════════════════════════════════
    #  Layout
    # ══════════════════════════════════════════════════════════════

    def _make_app(self) -> Application:
        # ── Header Bar ──
        # Design: beast mascot (2s rotation) + brand | separator | model + heartbeat + clock
        _BEASTS = [
            ("class:status-bar-beast-baihu",    "🐅"),
            ("class:status-bar-beast-qinglong", "🐉"),
            ("class:status-bar-beast-zhuque",   "🦅"),
            ("class:status-bar-beast-xuanwu",   "🐢"),
            ("class:status-bar-beast-qilin",    "🦄"),
            ("class:status-bar-beast-tengshe",  "🐍"),
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
            left_vis = 2 + 2 + len(f"CRUX Studio v{_CRUX_VERSION}")   # emoji(2) + spaces(2) + brand
            right_vis = 1 + len(model) + 1 + 2 + 1 + 5                 # space + model + space + pulse(2) + space + HH:MM
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
            if not self._activity_log:
                return FormattedText([])
            with self._state_lock:
                log_snapshot = list(self._activity_log)
            tw = _tw()
            spinner_char = self._spinner.current if self._spinner.running else " "
            pieces: list[tuple[str, str]] = []
            # Build single-line activity status
            has_running = False
            line = ""
            for icon, _style_class, msg in log_snapshot:
                if "●" in icon:
                    has_running = True
                    tag = f"{spinner_char} {msg}"
                else:
                    tag = f"{icon} {msg}"
                line += f" {tag} ·"
            line = line.rstrip(" ·")
            if len(line) > tw:
                line = line[: tw - 3] + "…"
            # Color based on content
            has_running = any("●" in icon for icon, _, _ in log_snapshot)
            has_error = any("✗" in icon for icon, _, _ in log_snapshot)
            if has_running:
                pieces.append(("class:activity-spinner", line))
            elif has_error:
                pieces.append(("class:activity-fail", line))
            else:
                pieces.append(("class:activity-done", line))
            return FormattedText(pieces)

        activity_window = Window(
            content=FormattedTextControl(_activity_content),
            height=lambda: 1 if self._activity_log else 0,
            style="class:message-area",
            always_hide_cursor=True,
        )

        # ── Activity separator ──
        def _activity_sep():
            if not self._activity_log:
                return FormattedText([])
            return FormattedText([("class:input-border", "─" * _tw())])

        activity_sep_window = Window(
            content=FormattedTextControl(_activity_sep),
            height=lambda: 1 if self._activity_log else 0,
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

        # We need dynamic height for multiline input; count newlines + 1
        def _input_height():
            text = self.input_buffer.text
            n_lines = text.count("\n") + 1
            return min(max(1, n_lines), 8)  # cap at 8 lines

        input_window = Window(
            content=input_ctrl,
            height=_input_height,
            style="class:input-field",
            dont_extend_height=True,
        )

        # ── Input border (bottom of input frame) ──
        def _input_bottom():
            tw = _tw()
            hint = " Enter 发送 │ Alt+Enter 换行 │ 鼠标/PgUp 滚屏 "
            hint_vis = 46
            bars_count = max(0, tw - hint_vis - 2)
            bars = "─" * bars_count
            return FormattedText([
                ("class:input-border", f"╚{bars}"),
                ("class:welcome-desc", hint),
                ("class:input-border", "╝"),
            ])

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

        # ── Assemble layout ──
        root = HSplit([
            ConditionalContainer(self._screen_window, filter=Condition(lambda: self.screen_stack.active)),
            header_window,
            header_sep_window,
            self.message_pane.pane,       # Messages + Welcome (weight=1)
            thinking_window,              # Thinking (0-N, conditional)
            activity_sep_window,          # Separator above activity
            activity_window,              # Activity (0-1, conditional)
            input_window,                 # Input (1-8)
            input_bottom_window,          # Input frame bottom
            status_window,                # Status (1)
        ])

        # On Windows with a Unix-like terminal (Git Bash, etc.), create_output()
        # defaults to Win32Output which fails. Force Vt100_Output instead.
        if _sys.platform == 'win32' and 'TERM' in os.environ:
            output = Vt100_Output.from_pty(_sys.stdout, term=os.environ.get('TERM'))
        else:
            output = create_output()

        return Application(
            layout=Layout(root),
            key_bindings=self.kb,
            style=build_style_v2(),
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
        if self._thinking:
            status_dot = ("class:status-bar-beast-qilin", "◉")
        else:
            status_dot = ("class:status-bar-beast-xuanwu", "●")

        model_str = self.session.model or "CRUX"
        cwd_str = str(Path.cwd())
        home = os.path.expanduser("~")
        if cwd_str.startswith(home):
            cwd_str = "~" + cwd_str[len(home):]
        git_str = self._cached_git

        # Right section: methodology + context + latency
        right_parts: list[tuple[str, str]] = []
        if _get_methodology_state is not None:
            try:
                ms = _get_methodology_state()
                level_map = {"micro": "A", "normal": "B", "complex": "C", "critical": "D"}
                level = level_map.get(ms.task_level.value, "")
                if level:
                    style_map = {"A": "class:status-bar-level-a", "B": "class:status-bar-level-b",
                                 "C": "class:status-bar-level-c", "D": "class:status-bar-level-d"}
                    right_parts.append((style_map.get(level, "class:status-bar"), f"[{level}]"))
            except Exception:
                pass

        bar = context_bar(self._cached_ctx_pct, width=8)
        right_parts.append(("class:status-bar-context", f" {bar} {self._cached_ctx_pct:.0f}%"))

        # ── Provider status ──
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            active = mgr.state.active
            circuit = mgr.state.circuit_state(active)
            if circuit != "CLOSED":
                right_parts.append(("class:status-bar-context", f" ⚡{active}⚠{circuit}"))
        except Exception:
            pass

        # ── Last run summary ──
        try:
            from core.run_summary import list_recent_runs
            runs = list_recent_runs(1)
            if runs:
                r = runs[0]
                status = r.get("status", "?")
                failed = r.get("failed", 0)
                total = r.get("total", 0)
                if failed > 0:
                    right_parts.append(("class:status-bar-level-d", f" run:{status} ✗{failed}/{total}"))
                else:
                    right_parts.append(("class:status-bar-level-a", f" run:{status} ✓{total}"))
        except Exception:
            pass

        # ── Provider latency ──
        try:
            from core.provider_history import get_all_stats
            stats = get_all_stats(5)
            latencies = [f"{pid}:{s.get('avg_latency_ms', 0):.0f}ms" for pid, s in list(stats.items())[:2] if s.get('avg_latency_ms')]
            if latencies:
                right_parts.append(("class:status-bar-context", " " + " ".join(latencies)))
        except Exception:
            pass

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
        """Render dashboard if active."""
        if not self._show_dashboard:
            from prompt_toolkit.formatted_text import FormattedText
            return FormattedText([])
        try:
            from ui.dashboard import render_dashboard
            return render_dashboard()
        except Exception as e:
            from prompt_toolkit.formatted_text import FormattedText
            return FormattedText([("class:header-error", f"Dashboard error: {e}")])


    def _on_accept(self, buf: Buffer) -> bool:
        buf.reset()
        if not text:
            return True

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
                iid = text[16:].strip()
                screen.run(iid) if hasattr(screen, 'run') else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            elif " " in text:
                cat = text.split(" ", 1)[1]
                screen.select(cat) if hasattr(screen, 'select') else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            else:
                screen.back() if hasattr(screen, 'back') else None
                self._toggle_screen("remediate")
            self._app.invalidate()
            return True
        if text == "/replay" or text.startswith("/replay "):
            screen = self._available_screens.get("replay")
            if " " in text:
                rid = text.split(" ", 1)[1]
                screen.select(rid) if hasattr(screen, 'select') else None
                if not self.screen_stack.active:
                    self.screen_stack.push(screen, self)
            else:
                screen.back() if hasattr(screen, 'back') else None
                self._toggle_screen("replay")
            self._app.invalidate()
            return True
        if text == "/recent-actions":
            try:
                from core.remediation_executor import get_recent_actions
                acts = get_recent_actions(15)
                lines = ["Recent Actions:"]
                lines.extend(f"  [{a.get('risk','?')}] {a.get('command','?'):40s} {a.get('status','?')}" for a in acts)
                self.message_pane.append_info("\\n".join(lines))
            except Exception as e:
                self.message_pane.append_error(f"Error: {e}")
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

        # ── Thinking guard ──
        if self._thinking:
            self.message_pane.append_info("Please wait — still processing previous request")
            return True

        # ── Submit for streaming ──
        with self._state_lock:
            self._activity_log.clear()
            self._thinking_buf = ""
            self._thinking = True
        self.thinking_panel.clear()
        self._streaming = True
        self.message_pane.append_message("user", text)
        self.message_pane.scroll_to_bottom()
        self._spinner.start()
        self._ui(self._refresh_status, _force=True)
        self._executor.submit(self._stream_response, text)
        return True

    def _send_image(self, image_path: str) -> None:
        if self._thinking:
            self.message_pane.append_info("Please wait — still processing previous request")
            return
        with self._state_lock:
            self._activity_log.clear()
            self._thinking = True
        self.thinking_panel.clear()
        fname = os.path.basename(image_path)
        self.message_pane.append_message("user", f"[图片: {fname}]")
        self.message_pane.scroll_to_bottom()
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
            self._activity_log.append(("●", "class:message-tool", f"视觉分析: {os.path.basename(image_path)}"))
            for kind, payload in self.session.send_stream(prompt, image_url=image_path):
                if kind == "text":
                    self._ui(self.message_pane.stream_append, str(payload))
                elif kind == "thinking":
                    self.thinking_panel.append(str(payload))
                elif kind == "info":
                    self._ui(self.message_pane.append_info, str(payload))
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
            if self._activity_log:
                last_icon, _, last_msg = self._activity_log[-1]
                if "●" in last_icon:
                    self._activity_log[-1] = ("✓", "class:activity-done", last_msg.replace("视觉分析: ", "视觉分析完成: "))
            self._ui(self.message_pane.stream_end, _force=True)
            self._ui(self.message_pane.scroll_to_bottom, _force=True)
        except Exception as e:
            self._ui(self.message_pane.append_error, f"图片分析失败: {e}", _force=True)
            self._activity_log.append(("✗", "class:activity-fail", f"视觉分析失败: {e}"))
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            with self._state_lock:
                self._streaming = False
                self._thinking = False
            self.thinking_panel.done()
            self._spinner.stop()
            self._ui(self._refresh_status, _force=True)

    def _stream_response(self, user_text: str) -> None:
        try:
            self._ui(self.message_pane.stream_start, "crux")
            pending_tool = None
            _t0 = time.monotonic()
            _first_token = False
            for kind, payload in self.session.send_stream(user_text):
                if not _first_token and kind in ("text", "thinking"):
                    _first_token = True
                    self._latency = time.monotonic() - _t0
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
                        pending_tool = tool_name
                        self._activity_log.append(("●", "class:activity-running", f"执行 {tool_name}"))
                    elif msg.startswith("正在生成"):
                        action = msg[2:].rstrip(".")
                        pending_tool = action
                        self._activity_log.append(("●", "class:activity-running", f"生成 {action}"))
                    elif "执行完成" in msg:
                        if pending_tool and self._activity_log:
                            last_icon, _, last_msg = self._activity_log[-1]
                            if "●" in last_icon:
                                self._activity_log[-1] = (
                                    "✓", "class:activity-done",
                                    last_msg.replace("执行 ", "").replace("生成 ", ""),
                                )
                        pending_tool = None
                    elif "fallback" in msg.lower() or "连接中断" in msg:
                        self._activity_log.append(("⚠", "class:activity-warn", msg[:100]))
                    elif "预算" in msg:
                        self._activity_log.append(("💰", "class:activity-info", msg[:100]))
                    else:
                        self._activity_log.append(("·", "class:activity-info", msg[:120]))
                    self._ui(lambda: None)
                elif kind == "tool_result":
                    if pending_tool and self._activity_log:
                        last_icon, _, last_msg = self._activity_log[-1]
                        if "●" in last_icon:
                            self._activity_log[-1] = (
                                "✓", "class:activity-done",
                                last_msg.replace("执行 ", "").replace("生成 ", ""),
                            )
                    pending_tool = None
                    self._ui(lambda: None)
                elif kind == "error":
                    self._ui(self.message_pane.append_error, str(payload))
                    self._activity_log.append(("✗", "class:activity-fail", str(payload)[:120]))
                elif kind in ("image", "video"):
                    d = payload if isinstance(payload, dict) else {}
                    loc = d.get("local_path", "") or d.get("url", "") or d.get("video_url", "")
                    if loc:
                        self._ui(self.message_pane.append_info, f"Saved: {loc}")
                        self._activity_log.append(("✓", "class:activity-done", f"已保存: {loc}"))
            # Mark any remaining pending tool as done
            if pending_tool and self._activity_log:
                last_icon, _, last_msg = self._activity_log[-1]
                if "●" in last_icon:
                    self._activity_log[-1] = ("✓", "class:activity-done", last_msg.replace("执行 ", "").replace("生成 ", ""))
            self._ui(self.message_pane.stream_end, _force=True)
            self._ui(self.message_pane.scroll_to_bottom, _force=True)
        except Exception as e:
            self._ui(self.message_pane.append_error, str(e), _force=True)
            self._activity_log.append(("✗", "class:activity-fail", f"异常: {e}"))
            self._ui(self.message_pane.stream_end, _force=True)
        finally:
            with self._state_lock:
                self._streaming = False
                self._thinking = False
            self.thinking_panel.done()
            self._spinner.stop()
            self._ui(self._refresh_status, _force=True)
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
            if a:
                fn(*a)
            else:
                fn()
        except Exception:
            logger.warning("TUI _ui callback failed", exc_info=True)
        try:
            if self._app and self._app.is_running:
                now = time.monotonic()
                if _force or not self._thinking or now - self._last_invalidate > 0.030:
                    self._last_invalidate = now
                    self._app.invalidate()
        except Exception:
            logger.warning("TUI _ui invalidate failed", exc_info=True)


    def _toggle_screen(self, name):
        screen = self._available_screens.get(name)
        if not screen:
            return
        if self.screen_stack.active and self.screen_stack.current.name == name:
            self.screen_stack.pop(self)
        else:
            self.screen_stack.push(screen, self)
        self._app.invalidate()
    def _on_spinner_tick(self) -> None:
        """Called by Spinner thread every ~80ms. Triggers activity bar repaint."""
        if self._activity_log and self._app and self._app.is_running:
            with contextlib.suppress(Exception):
                self._app.invalidate()

    def _refresh_status(self):
        self.status_bar.set_model(self.session.model)
        self.status_bar.set_thinking(self._thinking)
        # Cache context percentage
        try:
            chars = sum(len(str(m.get("content", ""))) for m in self.session.messages)
            self._cached_ctx_pct = min(100.0, chars * 0.4 / 128000 * 100)
            self.status_bar.set_context(int(chars * 0.4), 128000)
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        # Cache git info (call once, not per frame)
        self.status_bar.refresh()
        try:
            b = self.status_bar._branch
            d = self.status_bar._diff_stats
            self._cached_git = f" {b}" + (f" [{d}]" if d else "") if b else ""
        except Exception:
            self._cached_git = ""

    def run(self):
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
            self._app.run()
        except Exception as e:
            print(f"TUI error: {e}", file=sys.stderr)
            traceback.print_exc()
        finally:
            self._anim_running = False
            self._spinner.stop()
            self._executor.shutdown(wait=False)
