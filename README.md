# CRUX Studio v6.1

**AI-powered terminal coding assistant** — chat with your codebase, execute tools, review and fix bugs.

Built on DeepSeek V4 with a TUI (terminal UI), CRUX reads, writes, searches, runs tests, and orchestrates multi-agent workflows — all from your terminal.

## Quick Start

```bash
# Install
pip install -e .

# Set API key (interactive on first run, or use env var)
export DEEPSEEK_API_KEY=sk-your-key-here

# Launch
crux              # interactive TUI mode
crux chat         # chat mode
crux gen "a cat"  # image generation
```

On first run without an API key, CRUX will prompt you to paste your key.

## Requirements

- Python 3.11+
- DeepSeek API key ([get one here](https://platform.deepseek.com/api_keys))
- Windows / macOS / Linux

## Core Commands

| Command | Description |
|---------|-------------|
| `crux` | Interactive TUI (default) |
| `crux chat` | Chat mode with tool access |
| `crux gen "prompt"` | Generate an image |
| `crux video "prompt"` | Generate a video |
| `crux check` | Health check |
| `crux init` | Configure API key |
| `crux mcp-serve` | Start MCP server |

## Models

- **deepseek-v4-flash** — default, fast and cost-effective
- **deepseek-v4-pro** — auto-selected for complex tasks (refactoring, architecture)
- **agnes-2.0-flash** — vision model (image understanding)

CRUX auto-routes simple messages to flash and complex tasks to pro.

## Key Features

- **Chat with tools** — read/write files, run bash, search code, execute Python
- **Multi-agent orchestration** — parallel agents for complex tasks (requires confirmation)
- **Streaming TUI** — real-time thinking, tool progress, inline code display
- **Provider failover** — automatic switching when a model is unavailable
- **Test loop detection** — prevents fix-test-fail-fix infinite loops
- **Vision** — image understanding via agnes-2.0-flash

## Configuration

### API Keys

```bash
export DEEPSEEK_API_KEY=sk-xxx     # primary text model
export CRUX_API_KEY=sk-xxx         # vision + image generation (optional)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API key (required) |
| `CRUX_API_KEY` | — | CRUX/Agnes API key (for vision) |
| `CRUX_MAX_TOOL_LOOPS` | 40 | Max tool call rounds per turn |
| `CRUX_WORKSPACE` | cwd | Working directory |

## Architecture

```
crux_studio.py          # entry point
core/
  chat.py               # ChatSession — multi-turn conversation engine
  client.py             # HTTP client for DeepSeek / CRUX APIs
  tools.py              # ToolRegistry — 86 tools (bash, file, git, search)
  provider.py           # ProviderManager — model routing and failover
  stream_adapter.py     # SSE stream → event protocol
  runtime_orchestrator.py # multi-phase orchestration engine
ui/
  tui_app.py            # prompt_toolkit TUI application
  message_pane.py       # scrollable chat display
tests/
  test_integration_e2e.py   # 20 end-to-end scenarios
  test_stress_concurrency.py # 10 concurrency stress tests
  test_e2e_real_api.py  # 11 real API tests
```

## Development

```bash
# Run tests
pytest tests/ -q -m "not slow"

# Run with real API
DEEPSEEK_API_KEY=sk-xxx python output/crux_drive.py

# Run all tests including network
pytest tests/ -m "network"
```

## License

MIT
