"""IncidentPanel — Incident list with severity color coding and status filter.

Data source: core.incident_store (get_incident_trends, incident files)
Command: /incidents [open|acknowledged|closed]
"""

import json
import os


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


SEVERITY_STYLE = {
    "P0": "class:incident-p0",
    "P1": "class:incident-p1",
    "P2": "class:incident-p2",
}

STATUS_ICON = {
    "open": "●",
    "acknowledged": "◐",
    "closed": "✓",
}


def load_incidents(status_filter: str | None = None) -> list[dict]:
    """Load incidents from incident store, optional status filter."""
    from core.incident_store import INCIDENT_DIR
    if not os.path.isdir(INCIDENT_DIR):
        return []
    incidents = []
    for fname in os.listdir(INCIDENT_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(INCIDENT_DIR, fname), encoding="utf-8") as f:
                inc = json.load(f)
                if status_filter and inc.get("status") != status_filter:
                    continue
                incidents.append(inc)
        except Exception:
            continue
    return sorted(incidents, key=lambda x: x.get("created_at", ""), reverse=True)


def render_incidents(incidents: list[dict], width: int,
                     status_filter: str | None = None) -> list[tuple[str, str]]:
    """Render incident list with severity colors."""
    rows = []
    title = " INCIDENTS"
    if status_filter:
        title += f" / {status_filter}"
    rows.append(("class:panel-title", title + "\n"))
    rows.append(("class:muted", " SEV  STATUS        CREATED              SUMMARY\n"))

    for inc in incidents:
        sev = inc.get("severity", "P2")
        status = inc.get("status", "open")
        icon = STATUS_ICON.get(status, "•")
        created = str(inc.get("created_at", ""))[:19]
        summary = _shorten(inc.get("summary", ""), max(20, width - 44))
        style = SEVERITY_STYLE.get(sev, "class:incident-p2")

        rows.append((
            style,
            f" {sev:<3}  {icon} {status:<12} {created:<19}  {summary}\n",
        ))

    if not incidents:
        rows.append(("class:muted", " No incidents.\n"))

    return rows
