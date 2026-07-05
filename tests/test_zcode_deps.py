"""RED: pyproject.toml must include requests in project.dependencies."""

import pathlib

import tomllib  # Python 3.11+

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def test_requests_in_dependencies():
    """pyproject.toml [project] dependencies must include 'requests'."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps: list[str] = data.get("project", {}).get("dependencies", [])
    found = any(d.strip().lower().startswith("requests") for d in deps)
    assert found, f"'requests' not in pyproject.toml dependencies. Current: {deps}"
