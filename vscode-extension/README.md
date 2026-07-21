# CRUX Agent for VS Code

CRUX Studio AI Agent — your TUI engineering partner, now in VS Code.

## Features

- **Chat with CRUX** — send prompts and get AI-powered responses about your code
- **Code context** — select code in the editor and send it directly to the agent
- **VS Code native** — uses VS Code theme colors, keyboard shortcuts, and panel system

## Usage

- `Ctrl+Shift+A` — Open CRUX Agent panel
- Right-click selection → "CRUX: Send Selection to Agent"
- Command Palette → `CRUX: Open Agent Panel`

## Requirements

- Python 3.11+ with CRUX Studio dependencies
- CRUX Studio project (this extension communicates via `tools/crux_bridge.py`)

## Development

```bash
# Install vsce if not already
npm install -g @vscode/vsce

# Package the extension
vsce package

# Install locally
code --install-extension crux-agent-0.1.0.vsix
```
