"""CRUX MCP Servers — 外部工具桥接服务器集合。

每个子模块是一个独立的 MCP stdio 服务器，可被 CRUX 或其他 AI CLI 调用。

当前桥接列表:
- codebuddy_bridge   - CodeBuddy CLI (codebuddy_exec, codebuddy_review, codebuddy_search, codebuddy_status)
- aider_bridge       - Aider AI (aider_exec, aider_review, aider_status) [git-tracked edits]
"""
