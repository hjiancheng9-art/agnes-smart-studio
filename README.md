# CRUX Studio

**AI-powered terminal coding assistant** with self-healing infrastructure, MCP bridge, media generation, and multi-agent orchestration. Built on DeepSeek V4 with a terminal UI.

## Quick Start

```bash
pip install -e .
export DEEPSEEK_API_KEY=sk-your-key-here
crux              # interactive TUI
crux chat         # chat mode with tool access
crux gen "a cat"  # generate an image
```

On first run, CRUX prompts for your API key. Get one at [platform.deepseek.com](https://platform.deepseek.com/api_keys). Requires Python 3.11+.

## How CRUX works

```
You type → CRUX routes to right model (flash for simple, pro for complex)
         → Tools execute (read/write files, run shell, search code, call APIs)
         → Self-healing kicks in on failure (auto-fix → retry)
         → Result comes back in terminal
```

Three modes:
- **TUI** (`crux`): full terminal app with syntax highlighting, command palette, multi-pane layout
- **Chat** (`crux chat`): REPL-style conversation with tool access
- **Agent** (`crux --agent`): autonomous mode with external tools, multi-step planning

## MCP Integration

CRUX runs as an MCP server — connect Claude Code, Codex, or any MCP client:

```bash
# Start MCP server
crux mcp-serve

# Register in Claude Code
claude mcp add crux -- crux mcp-serve
```

Once connected, Claude Code can call CRUX's 190+ tools (code review, git ops, image/video generation, shell execution, web search) directly from your Claude session.

CRUX also connects to external MCP servers as a client — it auto-discovers tools from 8 bridges (Codex, Kimi, CodeBuddy, Aider, Claude Code, Qoder, ZCode, and itself).

## Self-Healing

CRUX monitors and repairs itself:

```
Tool fails → classify error → self_heal --fix → retry
Crash    → crash_guard captures → attempt auto-fix → log to incident store
CI job   → self-heal audit → silent-exception patching + ruff auto-fix
```

- **9 scanners**: syntax, silent exceptions, import errors, config drift, test failures, hook gaps, mojibake, global state leaks, flaky tests
- **Auto-fix**: silent exception logging, ruff violations
- **Recovery playbooks**: provider down, config corrupt, disk low, model error, rate limit, history corrupt

## CI Pipeline

7 GitHub Actions jobs on every push:

| Job | What it checks |
|-----|---------------|
| Quick Gate | Ruff lint + format + fast unit tests |
| Type Check | Pyright incremental (new errors only) |
| Test Matrix | Ubuntu/Windows × Python 3.11/3.12 |
| Integration | E2E + stress concurrency |
| Security | Bandit (hard gate) + Safety dependency scan |
| Encoding | Mojibake scan (zero tolerance) |
| Self-Heal | Audit + auto-fix + PR creation |

## Media Generation

```bash
# Image generation
crux gen "sunset over mountains, oil painting style" --size 1024x768

# Video generation
crux video "a cat walking through a garden" --duration 5

# Vision
crux vision photo.jpg "what's in this image?"

# Showrunner (full pipeline)
crux showrun "3-minute product demo with voiceover"
```

Supports text-to-image, image-to-image, text-to-video, image-to-video, and keyframe animation. Uses Agnes 2.0 Flash for vision and Agnes Image 2.1 / Video 2.0 for generation.

## Development

```bash
# Run tests
pytest tests/ -q -m "not slow" --timeout=30

# Run lint
ruff check core/ ui/

# Type check
pyright core/

# Full self-audit
python core/self_heal.py --fix

# Pre-commit
pre-commit run --all-files
```

See `HELP.md` for the full 58-command reference. Contributing: open a PR against `main`, CI must pass all 7 jobs.
