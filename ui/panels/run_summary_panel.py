"""RunSummaryPanel — Recent run/action summary with risk color, duration bar.

Data source: core.remediation_executor.get_recent_actions()
Command: /runs [limit]
"""


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _risk_style(risk: str) -> str:
    m = {"high": "class:run-error", "medium": "class:run-warn", "low": "class:run-success"}
    return m.get(risk, "class:muted")


def render_run_summary(actions: list[dict], width: int) -> list[tuple[str, str]]:
    """Render action log as structured panel."""
    rows = []
    rows.append(("class:panel-title", " RECENT ACTIONS\n"))
    rows.append((
        "class:muted",
        " RISK   STATUS      TIME                 COMMAND\n",
    ))

    for a in actions:
        risk = a.get("risk", "?")
        style = _risk_style(risk)
        status = a.get("status", "?")
        cmd = a.get("command", "?")
        ts = str(a.get("timestamp", a.get("time", "")))[:19]
        cmd_limit = max(12, width - 50)
        cmd = _shorten(cmd, cmd_limit)

        rows.append((
            style,
            f" {risk:<6} {status:<10} {ts:<19} {cmd}\n",
        ))

    if not actions:
        rows.append(("class:muted", " No actions yet.\n"))

    return rows
