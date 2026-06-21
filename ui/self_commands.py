"""Self-diagnose, heal, evolve, and matrix commands.

Extracted from ui/cli.py to keep the main CLI module manageable.
All functions take (cli_instance, session, arg) as parameters.
"""

import json
import os
import time

__all__ = [
    'cmd_pipe', 'cmd_self_audit', 'cmd_self_capability', 'cmd_self_diagnose', 'cmd_self_evolve', 'cmd_self_export', 'cmd_self_fix', 'cmd_self_heal', 'cmd_self_hygiene', 'cmd_self_matrix', 'cmd_self_recover', 'cmd_self_restore', 'cmd_self_save', 'cmd_self_sessions',
]



def cmd_self_capability(cli, session):
    """/self capability — show structured self-knowledge: skills, tools,
    providers, engines, models, environment, health."""
    from ui.display import console
    from core.capability import capability_snapshot
    snap = capability_snapshot()
    console.print("\n[bold cyan]Agnes Capability Snapshot[/]")
    for section in ("skills", "tools", "providers", "engines", "models", "environment", "health"):
        data = snap.get(section, {})
        if isinstance(data, dict):
            console.print(f"\n[bold]{section}[/] ({data.get('count', '?')} items)")
            if section == "health":
                for k, v in data.items():
                    console.print(f"  {k}: {v}")
    console.print()


def cmd_self_fix(cli, session):
    """/self fix — run audit then auto-fix mechanical issues."""
    from ui.display import show_info, console
    from core.self_audit import audit
    from core.self_fix import auto_fix
    show_info("Running audit + auto-fix...")
    report = audit()
    fixable = [f for f in report["findings"] if f.get("auto_fix")]
    if not fixable:
        console.print("[dim]No auto-fixable issues found.[/]")
        return
    console.print(f"[cyan]{len(fixable)} auto-fixable issues found.[/]")
    auto_fix(report["findings"], dry_run=False)
    from core.self_fix import SelfFixEngine
    SelfFixEngine().print_results()


def cmd_self_audit(cli, session):
    """/self audit — comprehensive codebase scan: imports, exceptions, files,
    config, skills, tests, encoding, git. Produces a prioritized report."""
    from ui.display import console, show_info
    from core.self_audit import audit, AuditEngine
    show_info("Running comprehensive self-audit...")
    t0 = time.time()
    report = audit()
    elapsed = time.time() - t0
    engine = AuditEngine()
    engine.print_report(report)
    console.print(f"[dim]Scan completed in {elapsed:.1f}s — {report['total_findings']} findings[/]")


def cmd_self_recover(cli, session):
    """/self recover <scenario> — run a recovery playbook."""
    from ui.display import console
    from core.recovery import recover
    scenarios = ["provider_down", "config_corrupt", "disk_low", "model_error"]
    console.print("[dim]Available scenarios: " + ", ".join(scenarios) + "[/]")
    # For now, run all applicable ones
    for s in scenarios:
        result = recover(s)
        icon = "[green]OK[/]" if result["success"] else "[red]FAIL[/]"
        console.print(f"  {icon} {s}: {result['message']}")


def cmd_self_hygiene(cli, session):
    """/self hygiene — run data rotation and cleanup."""
    from ui.display import show_info
    show_info("Running data hygiene...")


def cmd_self_sessions(cli, session):
    """/self sessions — list saved sessions."""
    from ui.display import console
    from core.session_mgr import session_list
    sessions = session_list()
    if not sessions:
        console.print("[dim]No saved sessions.[/]")
        return
    console.print("\n[bold]Saved Sessions[/]")
    for s in sessions:
        ts = __import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(s['saved_at']))
        console.print(f"  [cyan]{s['name']}[/] — {s['message_count']} msgs, {ts}")


def cmd_self_export(cli, session):
    """/self export — export conversation to Markdown."""
    from ui.display import show_info
    from core.export import export_chat
    path = export_chat(session.messages, "Agnes Chat Export")
    show_info(f"Exported to: {path}")


def cmd_self_save(cli, session):
    """/self save <name> — save current session."""
    from ui.display import show_info
    from core.session_mgr import session_save
    name = f"session_{int(__import__('time').time())}"
    saved = session_save(name, session.messages)
    show_info(f"Session saved as: {saved}")


def cmd_self_restore(cli, session):
    """/self restore <name> — restore a saved session."""
    from ui.display import show_error, console
    from core.session_mgr import session_list
    from core.monitor import hygiene_run
    sessions = session_list()
    if not sessions:
        show_error("No saved sessions.")
        return
    console.print("[dim]Usage: /self restore <name>[/]")
    for s in sessions:
        console.print(f"  [cyan]{s['name']}[/]")
    results = hygiene_run()
    for method, result in results.items():
        console.print(f"  [dim]{method}[/]: {result}")


def cmd_self_heal(cli, session):
    """/self heal — read error logs, locate problems, auto-fix."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from ui.display import show_success, console

    diagnostics = ["You are an Agnes Smart Studio maintainer. Analyze and fix all issues."]

    # 1. Error log
    err_file = os.path.join(root, "output", "last_error.txt")
    if os.path.exists(err_file):
        with open(err_file, encoding="utf-8") as fh:
            err_text = fh.read()[:3000]
        if err_text.strip():
            diagnostics.append(f"## Last error log\n```\n{err_text}\n```")

    # 2. Corrections
    sessions_file = os.path.join(root, "output", "sessions.json")
    if os.path.exists(sessions_file):
        try:
            with open(sessions_file, encoding="utf-8") as fh:
                data = json.loads(fh.read())
            corrections = data.get("corrections", [])[:5]
            if corrections:
                diag = "## Historical corrections\n"
                for c in corrections:
                    diag += f"- Problem: {c.get('what_happened', '')[:120]}\n"
                    diag += f"  Should: {c.get('what_should_happen', '')[:120]}\n"
                diagnostics.append(diag)
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # 3. Tool audit
    audit_file = os.path.join(root, "output", "tool_audit.jsonl")
    if os.path.exists(audit_file):
        try:
            failures = []
            with open(audit_file, encoding="utf-8") as fh:
                for line in fh:
                    entry = json.loads(line)
                    if not entry.get("success"):
                        failures.append(f"- {entry['tool']}: {entry.get('error', '')[:100]}")
            if failures:
                diagnostics.append("## Tool failures\n" + "\n".join(failures[-5:]))
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # 4. Startup checks
    try:
        from core.startup_checks import run_all
        results = run_all()
        warns = [f"- {cat}: {msg}" for cat, ok, msg in results if not ok]
        if warns:
            diagnostics.append("## Startup warnings\n" + "\n".join(warns))
    except (ImportError, OSError, RuntimeError):
        pass

    if len(diagnostics) == 1:
        show_success("No issues found, system healthy!")
        return

    prompt = "\n\n".join(diagnostics)
    prompt += "\n\nAnalyze each issue above. Use read_file and search_files to locate source code, edit_file to fix. Run test_smoke.py --quick to verify."

    console.print(f"[bold cyan]/self heal[/] analyzing {len(diagnostics)-1} diagnostic sources...")
    session.messages.append({"role": "user", "content": prompt})
    cli._stream_chat(session, prompt)


def cmd_self_evolve(cli, session):
    """/self evolve — analyze codebase, find improvement opportunities."""
    from ui.display import console

    prompt = """You are the Agnes self-evolution engine. Systematically review your codebase for improvements.

Steps:
1. search_files for TODO/FIXME/HACK/XXX markers
2. count_lines to identify bloated modules
3. glob_files to find .py files > 800 lines needing split
4. read_file test_smoke.py to check test coverage

Output: max 5 recommendations sorted by priority. Analysis only, do not modify code."""

    console.print("[bold cyan]/self evolve[/] scanning codebase...")
    session.messages.append({"role": "user", "content": prompt})
    cli._stream_chat(session, prompt)


def cmd_self_matrix(cli, session):
    """/matrix — capability matrix + detection + auto-repair."""
    prompt = """You are the Agnes capability matrix generator. Follow these steps:

## Step 1: Detection
1. run_python to ast.parse all .py files for syntax errors
2. env_check for environment
3. count_lines for module sizes
4. search_files for TODO/FIXME/HACK

## Step 2: Capability Matrix
Output a table showing all capabilities with status:
✅ Normal  ⚠️ Needs attention  ❌ Broken

## Step 3: Auto-repair
Fix clear issues directly:
- Syntax errors -> edit_file
- Format conflicts -> edit_file
- Missing deps -> pip_install
Fix without asking, report results when done."""

    session.messages.append({"role": "user", "content": prompt})
    cli._stream_chat(session, prompt)


def cmd_self_diagnose(cli, session, arg: str):
    """/self check|files|health|fix — various diagnostic commands."""
    from ui.display import show_success, show_warning, console
    from core.audit_runner import audit_syntax, project_tree_data, health_checks, collect_source_snippets

    arg = arg.strip()

    if arg == "check":
        errors = audit_syntax()
        if errors:
            show_warning(f"Found {len(errors)} syntax errors:")
            for e in errors:
                console.print(f"  FAIL {e}")
        else:
            show_success("All Python files pass syntax check")

    elif arg == "files":
        from rich.tree import Tree
        tree = Tree("[cyan]agnes-smart-studio[/]")
        for item in project_tree_data():
            if item["is_dir"]:
                branch = tree.add(f"[cyan]{item['name']}[/]")
                for sub in item["children"]:
                    if sub["is_dir"]:
                        branch.add(f"[cyan]{sub['name']}[/]")
                    else:
                        branch.add(f"[dim]{sub['name']}[/]")
            else:
                tree.add(f"[white]{item['name']}[/]")
        console.print(tree)

    elif arg == "health":
        for check in health_checks():
            icon = "OK" if check["ok"] else "FAIL"
            console.print(f"  {icon} {check['category']}: {check['message']}")

    elif arg == "fix":
        session.toggle_code_mode()
        ctx = "You are the Agnes Smart Studio maintainer. Analyze core source for bugs/compliance/optimization:\n\n"
        ctx += collect_source_snippets()
        console.print("[dim]AI analyzing source code...[/]")
        session.messages.append({"role": "user", "content": ctx})
        cli._stream_chat(session, ctx)

    else:
        show_warning("Usage: /self check|files|health|fix|heal|evolve")

def cmd_pipe(cli, session, arg: str):
    """/pipe <name> <input> -- run a predefined production pipeline."""
    from ui.display import console, show_info, show_error
    from core.pipeline_state import PipelineEngine, PIPELINES

    engine = PipelineEngine(cli)

    if not arg or arg == "pipe" or arg == "list":
        console.print()
        console.print("[bold]Available Pipelines[/]")
        for pid, pipe_data in PIPELINES.items():
            name = pipe_data.get("name", pid)
            count = len(pipe_data.get("skills", []))
            console.print("  [cyan]" + pid + "[/] -> " + name + " (" + str(count) + " skills)")
        console.print()
        console.print("Usage: /pipe <name> <your creative input>")
        return

    parts = arg.split(" ", 1)
    pipe_id = parts[0].strip()
    user_input = parts[1].strip() if len(parts) > 1 else ""

    if pipe_id not in PIPELINES:
        show_error("Unknown pipeline: " + pipe_id + ". Use /pipe list")
        return

    if not user_input:
        console.print("[dim]Enter your creative input for this pipeline[/]")
        return

    pipe_data = PIPELINES[pipe_id]
    name = pipe_data.get("name", pipe_id)
    count = len(pipe_data.get("skills", []))
    show_info("Running: " + name + " (" + str(count) + " skills)")

    def on_step(skill, status):
        if status == "loading":
            console.print("  [dim]-> " + skill + "...[/]", end=" ")
        elif status == "done":
            console.print("[green]OK[/]")

    state = engine.run(pipe_id, user_input, on_step=on_step)

    console.print()
    console.print("[bold green]Pipeline complete.[/]")
    console.print("  Steps: " + str(len(state.step_results)) + " ran")
    console.print("  QA checks: " + str(len(state.qa_log)))
    console.print("  Run ID: " + state.run_id)
    console.print("  Output: output/pipeline_runs/" + state.run_id + "/")
