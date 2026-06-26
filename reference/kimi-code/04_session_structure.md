# Kimi Code Session Structure

```
sessions/
  wd_{hash}/
    session_{uuid}/
      state.json    # title, createdAt, agents registry
      agents/
        main/
          wire.jsonl  # protocol wire log (metadata + config + tools + messages)
```

## state.json
```json
{
  "createdAt": "ISO 8601",
  "updatedAt": "ISO 8601",
  "title": "New Session",
  "isCustomTitle": false,
  "agents": {
    "main": {
      "homedir": "path/to/agents/main",
      "type": "main",
      "parentAgentId": null
    }
  },
  "custom": {}
}
```

## wire.jsonl Protocol
Line-based JSON protocol, 5 record types:
1. `metadata` - protocol_version, created_at
2. `config.update` (systemPrompt) - full system prompt + timestamp
3. `tools.set_active_tools` - tool name list + timestamp
4. `config.update` (thinkingLevel) - "high" thinking level
5. `user` / `assistant` / `tool_result` - conversation turns
