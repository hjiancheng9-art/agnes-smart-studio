"""RunDetailPanel — Full run details with actions."""


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def render_run_detail(run: dict, width: int) -> list[tuple[str, str]]:
    """Render a single run's full details."""
    rows = []
    status = run.get("status", "unknown")
    style = {"success": "class:run-success", "failover": "class:run-warn", "error": "class:run-error"}.get(
        status, "class:muted"
    )

    rows.append(("class:panel-title", " RUN DETAIL\n"))
    rows.append((style, f" status:        {status}\n"))
    rows.append(("class:muted", f" run_id:        {run.get('run_id', '-')}\n"))
    rows.append(("class:muted", f" root_trace:    {run.get('root_trace_id', '-')}\n"))
    rows.append(("class:muted", f" duration_ms:   {run.get('duration_ms', 0)}\n"))
    rows.append(("class:muted", f" total_tokens:  {run.get('total_tokens', 0)}\n"))

    chain = " → ".join(run.get("provider_chain", []) or ["-"])
    rows.append(("class:muted", f" provider:      {chain}\n"))
    tools = ", ".join(run.get("tools_called", []) or [])
    rows.append(("class:muted", f" tools:         {tools or '-'}\n"))

    quality = run.get("quality_status") or run.get("quality_score")
    if quality is not None:
        rows.append(("class:muted", f" quality:       {quality}\n"))

    inc_id = run.get("incident_id")
    if inc_id:
        rows.append(("class:incident-p1", f" incident:      {inc_id}  → /incident {inc_id}\n"))

    trace = run.get("root_trace_id", "-")
    rows.append(("", "\n"))
    rows.append(("class:panel-title", " ACTIONS\n"))
    rows.append(("class:muted", f" /route {trace} │ /replay {trace}\n"))

    return rows
