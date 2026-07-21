"""CRUX bootstrap utilities — extracted from crux_studio.py to reduce entry-point bloat.

Phase 1 of entry-point refactoring: output helpers + startup health check.
Phase 2 (deferred): extract chat mode runners (_chat_repl, _chat_tui, etc.).
"""

from pathlib import Path


def safe_rich_print():
    """Return a print function that uses Rich if available, plain print otherwise.

    Falls back to plain print() on ANY Rich failure — not just ImportError.
    Windows terminals can trigger OSError (errno 22) when Rich's Win32 console
    API calls fail on non-standard terminal emulators.
    """
    try:
        from rich.console import Console

        rc = Console(highlight=False)

        def _rp(text: str = "", **kwargs) -> None:
            try:
                rc.print(text, **kwargs)
            except Exception:
                # Rich failed to render — fall back to plain print
                print(text)

        return _rp
    except ImportError:
        return print


def print_kimi_tree(root: Path, max_depth: int = 2) -> None:
    """Print a Kimi-style directory tree (first N levels, censored hidden dirs)."""

    SKIP_DIRS = {
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        "egg-info",
    }
    SKIP_FILES = {".DS_Store", "Thumbs.db", "nul", "python"}

    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        print("  (permission denied)")
        return

    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file() and e.name not in SKIP_FILES]

    lines: list[str] = []
    shown = 0
    FILE_CAP = 20
    DIR_CAP = 40

    for entry in dirs:
        if shown >= DIR_CAP:
            remaining_dirs = len(dirs) - shown
            lines.append(f"  ... and {remaining_dirs} more directories")
            break
        name = entry.name
        marker = "/" if entry.is_dir() else ""
        lines.append(f"  {name}{marker}")
        if max_depth > 1 and not name.startswith(".") and name not in SKIP_DIRS:
            try:
                sub_entries = sorted(entry.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                shown += 1
                continue
            sub_count = 0
            SUB_CAP = 15
            for sub in sub_entries:
                if sub_count >= SUB_CAP:
                    remaining = len(sub_entries) - sub_count
                    lines.append(f"      ... and {remaining} more")
                    break
                sub_name = sub.name
                if sub.is_dir():
                    lines.append(f"      {sub_name}/")
                elif sub_name not in SKIP_FILES:
                    lines.append(f"      {sub_name}")
                    sub_count += 1
        shown += 1

    for shown_files, entry in enumerate(files):
        if shown_files >= FILE_CAP:
            remaining_files = len(files) - shown_files
            lines.append(f"  ... and {remaining_files} more files")
            break
        lines.append(f"  {entry.name}")

    for line in lines:
        print(line)


def print_skills_summary() -> None:
    """Print available skills grouped by scope (Kimi-style)."""
    builtin_skills = ["update-config", "write-goal"]

    project_dir = Path(__file__).parent.parent / "skills"
    project_skills: list[str] = []
    if project_dir.exists():
        for f in sorted(project_dir.glob("*.skill.json")):
            project_skills.append(f.stem.replace(".skill", ""))
        for f in sorted(project_dir.glob("*.skill.md")):
            project_skills.append(f.stem.replace(".skill", ""))

    marketplace_count = 668

    print(
        f"  Scope: Built-in ({len(builtin_skills)})  |  "
        f"Project ({len(project_skills)})  |  Marketplace ({marketplace_count})"
    )
    if project_skills:
        shown = project_skills[:8]
        print(f"  Project skills: {', '.join(shown)}" + ("..." if len(project_skills) > 8 else ""))
    print(f"  Built-in: {', '.join(builtin_skills)}")
    print()
    print("  Use /skill list to browse, /skill load <name> to activate.")


def run_startup_health() -> None:
    """Lightweight health check before entering REPL — silent, logs only."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        from core.mcp_client import _mcp_client, ensure_mcp_servers

        ensure_mcp_servers()

        if _mcp_client is not None and len(_mcp_client._servers) > 5:
            old = len(_mcp_client._servers)
            n = _mcp_client.reload_config()
            logger.info("bootstrap: MCP config reloaded (%d -> %d)", old, n)

        try:
            from core.startup_checks import _check_core_imports

            _check_core_imports()
        except Exception:
            logger.debug("bootstrap: DNA check skipped", exc_info=True)

        logger.debug("bootstrap health check complete")
    except Exception:
        logger.debug("bootstrap health check skipped", exc_info=True)
