"""DashboardScreen — Aggregated view of system status.

Sections: Recent Runs, Open Incidents, Provider Health.
Keyboard: R refresh, Q/Escape back.
"""


class DashboardScreen:
    """Read-only dashboard aggregating runs, incidents, provider health."""

    name = "dashboard"

    def __init__(self):
        self._runs: list[dict] = []
        self._incidents: list[dict] = []
        self._providers: list[dict] = []

    def refresh(self) -> None:
        """Pull fresh data from backend stores."""
        try:
            from core.remediation_executor import get_recent_actions
            self._runs = get_recent_actions(5)
        except Exception:
            self._runs = []
        try:
            from ui.panels.incident_panel import load_incidents
            self._incidents = load_incidents("open")[:5]
        except Exception:
            self._incidents = []

    def render(self, width: int) -> list[tuple[str, str]]:
        """Render dashboard as a list of (style, text) pairs."""
        pieces = []
        pieces.append(("class:panel-title", " CRUX DASHBOARD\n"))
        pieces.append(("class:muted", " R refresh │ Q/Esc back │ /run last │ /route last │ /incidents open\n\n"))

        # ── Recent Runs ──
        from ui.panels.run_summary_panel import render_run_summary
        pieces.extend(render_run_summary(self._runs, width))
        pieces.append(("", "\n"))

        # ── Open Incidents ──
        from ui.panels.incident_panel import render_incidents
        pieces.extend(render_incidents(self._incidents, width, status_filter="open"))

        return pieces

    def handle_key(self, key: str) -> bool:
        """Handle keyboard shortcuts. Returns True if handled."""
        return False

    def on_exit(self, app) -> None:
        app.invalidate()
