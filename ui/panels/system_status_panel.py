"""SystemStatusPanel — Provider health, circuit breaker, latency overview."""


def _shorten(text: object, limit: int = 60) -> str:
    value = str(text).replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def render_system_status(providers: list[dict], width: int) -> list[tuple[str, str]]:
    """Render provider health/circuit status."""
    rows = []
    rows.append(("class:panel-title", " PROVIDER HEALTH\n"))
    rows.append(("class:muted", " PROVIDER              HEALTH   CIRCUIT      LATENCY   STATUS\n"))

    for p in providers:
        name = p.get("provider", p.get("name", "-"))
        health = float(p.get("health_score", 0.0) or 0.0)
        circuit = p.get("circuit_state", p.get("circuit", "unknown"))
        latency = int(p.get("latency_ema_ms", 0) or 0)
        status = p.get("status", circuit)

        if circuit == "OPEN":
            style = "class:provider-open"
        elif circuit == "HALF_OPEN":
            style = "class:provider-half-open"
        elif health >= 0.8:
            style = "class:provider-ok"
        else:
            style = "class:provider-warn"

        rows.append((
            style,
            f" {name:<21} {health:>5.2f}    {circuit:<11} {latency:>5}ms   {status}\n",
        ))

    if not providers:
        rows.append(("class:muted", " No provider status available.\n"))

    return rows
