"""
CRUX Dashboard — Problem-Oriented State Panel (v2)
====================================================
Per 3-platform debate consensus:
- "平时安静，出事说话" (Quiet normally, speak up on problems)
- Normal state: compact, 3 key indicators only
- Active state: show tool call chains, timing
- Error state: auto-expand diagnostics
- Automatically adjusts content based on system state

Content priority (P0→P5):
  P0: Context usage %            — always in status bar
  P1: Active agent count / task  — what is the system doing
  P2: ComfyUI status             — model/queue health
  P3: TRM route status            — tool call chain
  P4: Quest progress             — long task status
  P5: CPU/memory                 — removed by default
"""

import time

from ui.responsive import LayoutConfig


class DashboardState:
    """
    Tracks system state to determine what dashboard should show.

    States:
        idle      → compact (3 indicators, no animation)
        active    → show tool calls, agent status (medium detail)
        streaming → show model output info
        error     → auto-expand, show error chain
        thinking  → show reasoning progress

    Secondary panel (collapsible): CPU, memory, disk metrics — P5, hidden by default.
    """

    def __init__(self):
        self._state = "idle"  # idle | active | streaming | error | thinking
        self._last_state_change = time.monotonic()
        self._tool_name = ""
        self._tool_status = ""
        self._error_msg = ""
        self._agent_count = 0
        self._context_pct = 0.0
        self._comfyui_status = "unknown"
        self._comfyui_queue = 0
        self._trm_active = 0
        self._quest_progress = ""

        # Activity pulse — stays highlighted for 2s after last activity
        self._last_activity = 0.0
        self._activity_decay = 2.0

        # ── Secondary metrics (collapsible, P5 per debate) ──
        self._show_secondary = False
        self._cpu_pct = 0.0
        self._memory_pct = 0.0
        self._memory_used_mb = 0
        self._memory_total_mb = 8192
        self._disk_pct = 0.0
        self._process_count = 0
        self._uptime_hours = 0.0

    def toggle_secondary(self):
        """Toggle secondary metrics panel visibility."""
        self._show_secondary = not self._show_secondary

    def update_secondary(self, cpu=0, mem_pct=0, mem_used=0, mem_total=8192, disk=0, processes=0, uptime=0):
        """Bulk-update secondary metrics."""
        self._cpu_pct = cpu
        self._memory_pct = mem_pct
        self._memory_used_mb = mem_used
        self._memory_total_mb = mem_total
        self._disk_pct = disk
        self._process_count = processes
        self._uptime_hours = uptime

    def set_state(self, state: str):
        """idle | active | streaming | error | thinking"""
        self._state = state
        self._last_state_change = time.monotonic()

    def set_activity(self, tool_name: str = "", status: str = ""):
        """Mark recent activity (dashboard will highlight for 2s)."""
        self._last_activity = time.monotonic()
        if tool_name:
            self._tool_name = tool_name
            self._tool_status = status
        self.set_state("active")

    def set_error(self, msg: str):
        self._error_msg = msg
        self.set_state("error")

    def clear_error(self):
        self._error_msg = ""
        if self._state == "error":
            self.set_state("idle")

    def update_metrics(self, **kwargs):
        """Bulk-update metrics from external poll."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    @property
    def is_hot(self) -> bool:
        """Whether dashboard should be auto-visible."""
        return (
            self._state in ("error", "active", "thinking")
            or time.monotonic() - self._last_activity < self._activity_decay
        )

    @property
    def state(self) -> str:
        return self._state

    @property
    def error_msg(self) -> str:
        return self._error_msg

    @property
    def context_pct(self) -> float:
        return self._context_pct


# ── Render ────────────────────────────────────────────────


def _tw() -> int:
    """Terminal width (fallback 120 if undetectable)."""
    import shutil

    return shutil.get_terminal_size().columns


def render_dashboard(state: DashboardState | None = None, layout: LayoutConfig | None = None) -> list[tuple[str, str]]:
    """
    Render dashboard content based on current state and layout config.

    Returns list of (style, text) tuples for FormattedTextControl.

    Modes:
        compact   → 3 key indicators (context%, agent, status)
        expanded  → full panel with all sections
        error     → auto-expanded with error diagnostics
    """
    if state is None:
        state = DashboardState()

    is_compact = layout and layout.dashboard_compact
    is_visible = layout and layout.dashboard_visible

    if not is_visible:
        return []

    lines: list[tuple[str, str]] = []
    sep = ("class:dim", " " + "─" * 20 + "\n")

    # ── Top state indicator ─────────────────────────
    if state.state == "error":
        lines.append(("class:error bold", " ⚠ ERROR DETECTED\n"))
    elif state.state == "active":
        lines.append(("class:success", " ● ACTIVE\n"))
    elif state.state == "streaming":
        lines.append(("class:info", " ▶ STREAMING\n"))
    elif state.state == "thinking":
        lines.append(("class:thinking italic", " … THINKING\n"))

    # ── Key indicators (always visible, even in compact) ──
    lines.append(("class:header-bar bold", " STATUS\n"))
    lines.append(sep)

    # Context usage — P0
    ctx_pct = state.context_pct
    if ctx_pct > 85:
        ctx_style = "class:error bold"
    elif ctx_pct > 65:
        ctx_style = "class:warn"
    else:
        ctx_style = "class:ok"
    lines.append((ctx_style, f"  Context: {ctx_pct:.0f}%\n"))

    # Agent count — P1
    lines.append(("", f"  Agents:  {state._agent_count}\n"))

    # Status line
    status_text = state._tool_status or "idle"
    lines.append(("class:dim", f"  Status:  {status_text}\n"))

    if is_compact:
        # Compact mode — just 3 indicators, done
        lines.append(sep)
        return lines

    # ── Expanded sections ──────────────────────────────

    # Tool call chain
    if state._tool_name or state._state == "active":
        lines.append(("\n", ""))
        lines.append(("class:header-bar bold", " TOOL\n"))
        lines.append(sep)
        if state._tool_name:
            lines.append(("class:info", f"  {state._tool_name}\n"))
        else:
            lines.append(("class:dim", "  (waiting)\n"))

    # ComfyUI
    if state._comfyui_status != "unknown":
        lines.append(("\n", ""))
        lines.append(("class:header-bar bold", " COMFYUI\n"))
        lines.append(sep)
        status_color = "class:ok" if state._comfyui_status == "ok" else "class:error"
        lines.append((status_color, f"  {state._comfyui_status}\n"))
        if state._comfyui_queue > 0:
            lines.append(("class:warn", f"  Queue: {state._comfyui_queue}\n"))

    # Error diagnostics (auto-expanded)
    if state.state == "error" and state.error_msg:
        lines.append(("\n", ""))
        lines.append(("class:error bold", " ⚠ ERROR\n"))
        lines.append(sep)
        # Show first 200 chars of error
        err = state.error_msg[:200]
        lines.append(("class:error", f"  {err}\n"))

    # ── Secondary metrics (collapsible, P5 per debate) ──
    if state._show_secondary:
        lines.append(("\n", ""))
        lines.append(("class:header-bar bold", " SYSTEM\n"))
        lines.append(sep)
        cpu_c = "class:ok" if state._cpu_pct < 70 else ("class:warn" if state._cpu_pct < 90 else "class:error")
        lines.append((cpu_c, f"  CPU:     {state._cpu_pct:.0f}%\n"))
        mem_c = "class:ok" if state._memory_pct < 70 else ("class:warn" if state._memory_pct < 90 else "class:error")
        lines.append(
            (mem_c, f"  Memory:  {state._memory_pct:.0f}% ({state._memory_used_mb}MB/{state._memory_total_mb}MB)\n")
        )
        disk_c = "class:ok" if state._disk_pct < 80 else ("class:warn" if state._disk_pct < 95 else "class:error")
        lines.append((disk_c, f"  Disk:    {state._disk_pct:.0f}%\n"))
        lines.append(("class:dim", f"  Procs:   {state._process_count}\n"))
        if state._uptime_hours > 0:
            lines.append(("class:dim", f"  Uptime:  {state._uptime_hours:.1f}h\n"))
        lines.append(("class:dim", "  [Tab] hide\n"))

    lines.append(sep)
    return lines
