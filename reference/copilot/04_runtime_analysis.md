# Copilot CLI Runtime Analysis

## Version Info
- Version: **1.0.65**
- Node.js: v24.16.0
- Platform: win32/x64
- Model: **gpt-5-mini**

## Key Features
- **Context Window**: 128,000 tokens
- **Compaction**: Auto at 80% utilization
- **MCP**: Remote `github-mcp-server` at `api.individual.githubcopilot.com/mcp/readonly`
- **Memory**: Disabled (ExP gate)
- **Permissions**: Permission service per session
- **Login**: GitHub OAuth
- **Commands**: `/login`, `/usage`, `/tasks`

## Hook System
- `postToolUse` hook type observed
- Runs after each tool execution
- Hook input includes: sessionId, timestamp, cwd
