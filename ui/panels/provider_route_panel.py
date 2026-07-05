"""ProviderRoutePanel — Provider failover chain visualization.

Data source: core.session_wire traces
Command: /route last | /route <root_trace_id>
"""


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def render_provider_route(route: dict, width: int) -> list[tuple[str, str]]:
    """Render provider route chain with success/fail indicators."""
    rows = []
    rows.append(("class:panel-title", " PROVIDER ROUTE\n"))

    attempts = route.get("attempts", [])

    for i, attempt in enumerate(attempts, 1):
        provider = attempt.get("provider", "-")
        model = attempt.get("model", "-")
        status = attempt.get("status", "unknown")
        latency = attempt.get("latency_ms", 0)
        reason = attempt.get("reason") or attempt.get("error") or ""

        if status == "success":
            icon = "✓"
            style = "class:route-success"
        elif status in {"timeout", "error", "failed"}:
            icon = "✗"
            style = "class:route-fail"
        elif status in {"skipped", "circuit_open"}:
            icon = "⊘"
            style = "class:route-skip"
        else:
            icon = "•"
            style = "class:muted"

        reason = _shorten(reason, max(20, width - 48))

        rows.append((
            style,
            f" {i:>2}. {icon} {provider:<16} {model:<20} {status:<12} {latency:>6}ms {reason}\n",
        ))

    if not attempts:
        rows.append(("class:muted", " No provider route recorded.\n"))

    return rows
