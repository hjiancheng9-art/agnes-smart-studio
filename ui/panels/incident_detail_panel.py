"""IncidentDetailPanel — Full incident details with playbook and actions."""

import textwrap


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _wrap(text: object, width: int) -> str:
    value = str(text)
    lines = textwrap.wrap(value, width=max(20, width - 2)) or [""]
    return "\n".join(f" {line}" for line in lines) + "\n"


def render_incident_detail(incident: dict, width: int) -> list[tuple[str, str]]:
    """Render single incident with full info."""
    rows = []
    sev = incident.get("severity", "P2")
    style = {"P0": "class:incident-p0", "P1": "class:incident-p1",
             "P2": "class:incident-p2"}.get(sev, "class:muted")

    rows.append(("class:panel-title", " INCIDENT DETAIL\n"))
    rows.append((style, f" severity:    {sev}\n"))
    rows.append(("class:muted", f" id:          {incident.get('id', '-')}\n"))
    rows.append(("class:muted", f" status:      {incident.get('status', '-')}\n"))
    rows.append(("class:muted", f" created_at:  {incident.get('created_at', '-')}\n"))
    rows.append(("class:muted", f" resolved_at: {incident.get('resolved_at', '-') or '-'}\n"))
    rows.append(("class:muted", f" type:        {incident.get('incident_type', '-')}\n"))
    rows.append(("class:muted", f" owner:       {incident.get('owner', '-')}\n"))
    rows.append(("class:muted", f" root_trace:  {incident.get('root_trace_id', '-')}\n"))

    rows.append(("", "\n"))
    rows.append(("class:panel-title", " SUMMARY\n"))
    summary = incident.get("summary", "-")
    if isinstance(summary, str):
        rows.append(("class:muted", _wrap(summary, width)))

    evidence = incident.get("evidence")
    if evidence:
        rows.append(("", "\n"))
        rows.append(("class:panel-title", " EVIDENCE\n"))
        rows.append(("class:muted", _wrap(evidence, width)))

    rows.append(("", "\n"))
    rows.append(("class:panel-title", " ACTIONS\n"))
    inc_id = incident.get("id", "-")
    trace = incident.get("root_trace_id", "-")
    rows.append(("class:muted", f" /remediate {inc_id} --dry-run\n"))
    rows.append(("class:muted", f" /replay {trace} │ /route {trace}\n"))

    return rows
