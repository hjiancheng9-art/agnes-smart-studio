"""CRUX Dashboard — 实时状态面板, 聚合后端 P0-P21 关键信息."""

import time
from typing import Any

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.containers import Window, HSplit, VSplit
from prompt_toolkit.layout.controls import FormattedTextControl


def _tw() -> int:
    """Get terminal width, fallback to 80."""
    try:
        import shutil
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def render_dashboard() -> FormattedText:
    """Render the full dashboard as formatted text."""
    tw = _tw()
    lines: list[tuple[str, str]] = []
    sep = ("class:dim", f"{'─' * min(tw, 80)}\n")

    # ── Provider Status ──
    lines.append(("class:header-bar bold", " PROVIDER STATUS\n"))
    lines.append(sep)
    try:
        from core.provider import get_provider_manager
        mgr = get_provider_manager()
        all_pids = list(mgr.providers.keys())
        for pid in all_pids:
            circuit = mgr.state.circuit_state(pid)
            if circuit == "CLOSED":
                dot, style = "●", "class:ok"
            elif circuit == "HALF_OPEN":
                dot, style = "◉", "class:warn"
            else:
                dot, style = "○", "class:header-error"
            active = " ← active" if pid == mgr.state.active else ""
            lines.append((style, f"  {dot} {pid}{active}\n"))

        # Latency
        try:
            from core.provider_history import get_all_stats
            stats = get_all_stats(5)
            for pid in all_pids:
                s = stats.get(pid, {})
                if s.get("calls", 0) > 0:
                    lat = s.get("avg_latency_ms", 0)
                    rate = s.get("success_rate", 1.0)
                    cf = s.get("consecutive_failures", 0)
                    lines.append(("class:dim", f"       latency={lat:.0f}ms  success={rate:.0%}  fails={cf}\n"))
        except Exception:
            pass
    except Exception:
        lines.append(("class:dim", "  (provider manager unavailable)\n"))

    # ── Last Run ──
    lines.append(("\n", ""))
    lines.append(("class:header-bar bold", " LAST RUN\n"))
    lines.append(sep)
    try:
        from core.run_summary import list_recent_runs
        runs = list_recent_runs(1)
        if runs:
            r = runs[0]
            status = r.get("status", "?")
            total = r.get("total", 0)
            failed = r.get("failed", 0)
            skipped = r.get("skipped", 0)
            dur = r.get("duration_ms", 0)
            rid = r.get("root_trace_id", "")[:12]

            s_style = "class:ok" if failed == 0 else "class:header-error"
            lines.append((s_style, f"  Status: {status}  [{rid}]\n"))
            lines.append(("", f"  Tasks: {total} total / {total - failed - skipped} done"))
            if failed:
                lines.append(("class:header-error", f" / {failed} failed"))
            if skipped:
                lines.append(("class:warn", f" / {skipped} skipped"))
            lines.append(("\n", "\n"))
            lines.append(("class:dim", f"  Duration: {dur}ms\n"))

            # Quality + Policy (from stored summary)
            try:
                from core.run_replay import load_replay
                replay = load_replay(rid)
                if replay:
                    summary = replay.get("summary", {})
                    qs = summary.get("quality_status", "")
                    if qs:
                        q_style = "class:ok" if qs == "success" else "class:warn"
                        lines.append((q_style, f"  Quality: {qs} ({summary.get('quality_score', 0)})\n"))
                    pa = summary.get("policy_action", "")
                    if pa:
                        lines.append(("", f"  Policy: {pa}  ({summary.get('policy_reason', '')})\n"))
                    inc = summary.get("incident", {})
                    if inc and inc.get("total_incidents", 0) > 0:
                        lines.append(("class:header-error", f"  Incident: {inc['primary_category']} ({inc['total_incidents']}x)\n"))
            except Exception:
                pass
        else:
            lines.append(("class:dim", "  No runs yet.\n"))
    except Exception:
        lines.append(("class:dim", "  (run history unavailable)\n"))

    # ── Incidents (24h) ──
    lines.append(("\n", ""))
    lines.append(("class:header-bar bold", " INCIDENTS (24h)\n"))
    lines.append(sep)
    try:
        from core.incident_store import get_incident_trends, INCIDENT_FILE
        import os
        if os.path.exists(INCIDENT_FILE):
            trends = get_incident_trends(24)
            if trends["total"] > 0:
                for cat, cnt in trends["by_category"].items():
                    s = "class:header-error" if cnt >= 3 else "class:warn" if cnt >= 1 else "class:dim"
                    lines.append((s, f"  {cat}: {cnt}x\n"))
                lines.append(("class:dim", f"  Total: {trends['total']} incidents\n"))
            else:
                lines.append(("class:ok", "  No incidents in last 24h\n"))
        else:
            lines.append(("class:dim", "  No incident history.\n"))
    except Exception:
        lines.append(("class:dim", "  (incident store unavailable)\n"))

    # ── Active Alerts ──
    lines.append(("\n", ""))
    lines.append(("class:header-bar bold", " ALERTS\n"))
    lines.append(sep)
    try:
        from core.incident_store import get_incident_trends
        trends = get_incident_trends(1)  # last hour
        has_alerts = False
        for cat, cnt in trends.get("by_category", {}).items():
            if cnt >= 3:
                lines.append(("class:header-error bold", f"  ! {cat}: {cnt}x in last hour (threshold 3)\n"))
                has_alerts = True
        if not has_alerts:
            lines.append(("class:ok", "  No active alerts.\n"))
    except Exception:
        pass

    # ── Quick Actions ──
    lines.append(("\n", ""))
    lines.append(("class:header-bar bold", " QUICK ACTIONS\n"))
    lines.append(sep)
    actions = [
        ("/providers", "View full provider health"),
        ("/runs", "View run history"),
        ("/summary <id>", "View run summary"),
        ("/replays", "List saved replays"),
        ("/replay <id>", "View replay timeline"),
        ("/incidents", "View incident trends"),
        ("/playbook <type>", "View remediation guide"),
    ]
    for cmd, desc in actions:
        lines.append(("class:status-bar-git", f"  {cmd:20s}"))
        lines.append(("class:dim", f" {desc}\n"))

    return FormattedText(lines)
