# Copilot CLI Tools

## Core Tools
- **powershell** — Primary shell executor (Windows native, Git Bash via powershell)
  - `mode=sync`: Quick commands, 30s default initial_wait
  - `mode=async`: Long-lived processes (servers/watchers)
  - `detach: true`: Persistent daemons survive session shutdown
- **read_powershell** — Retrieve output from running shell
- **stop_powershell** — Kill running shell by shellId
- **view** — Read files (20KB truncation, parallel safe)
- **view_range** — Read file sections
- **edit** — Batch edits to same file (sequential order, parallel safe)
- **fetch_copilot_cli_documentation** — Self-documentation tool
- **ask_user** — Structured questions with choices
- **task** — Sub-agent delegation (explore agents, custom agents)
- **read_agent** — Read async agent output

## System Tools
- `git`, `curl`, `gh` — Available as system commands

## SQL Tools (embedded via system_reminder)
- **todos** table — Task management with status tracking
- **todo_deps** table — Task dependency graph
- **inbox** table — User messages/notifications
- **session_state** table — Key-value persistent state

## Agent System
- Built-in `explore` agent: Read-only, fast codebase search
- Custom agents take priority over built-in
- Background agents enable parallel work
- Agent scope ownership: once delegated, don't investigate same scope
