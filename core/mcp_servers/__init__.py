"""CRUX MCP Servers — 外部工具桥接服务器集合。

每个子模块是一个独立的 MCP stdio 服务器，可被 CRUX 或其他 AI CLI 调用。

当前桥接列表:
- codex_bridge       - OpenAI Codex CLI (codex_exec, codex_review, codex_think, codex_status) [PTY required]
- kimi_bridge        - Moonshot Kimi CLI (kimi_exec, kimi_review, kimi_status, kimi_login)
- copilot_bridge     - GitHub Copilot CLI (copilot_*)
- qoder_bridge       - Qoder CLI (qoder_exec, qoder_review, qoder_status, qoder_plan, qoder_search)
- codebuddy_bridge   - CodeBuddy CLI (codebuddy_exec, codebuddy_review, codebuddy_search, codebuddy_status)
"""

