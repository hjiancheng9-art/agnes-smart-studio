# Copilot CLI Config Structure

## ~/.copilot/

```
.copilot/
├── config.json          # Auto-managed (firstLaunchAt, login state)
├── command-history-state.json  # Command history array
├── session-store.db     # SQLite session store
├── session-store.db-shm
├── session-store.db-wal
├── ide/                 # IDE integration (empty)
├── logs/                # Per-process logs
│   └── process-{timestamp}-{pid}.log
└── session-state/       # All sessions
    └── {session-uuid}/
        ├── workspace.yaml      # Session metadata
        ├── inuse.{pid}.lock    # Process lock file
        ├── session.db          # Per-session SQLite
        ├── events.jsonl        # Full event stream
        ├── checkpoints/
        │   └── index.md        # Checkpoint history
        ├── files/              # Session artifacts
        └── research/           # Research cache
```

## workspace.yaml

```yaml
id: {uuid}
cwd: {working directory}
client_name: github/cli
name: {session title}
user_named: false
summary_count: 0
created_at: ISO 8601
updated_at: ISO 8601
```
