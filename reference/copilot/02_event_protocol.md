# Copilot CLI Event Protocol

## Event Types

0. `session.start`
1. `session.error`
2. `session.info`
3. `session.info`
4. `session.model_change`
5. `system.message`
6. `user.message`
7. `assistant.turn_start`
8. `assistant.message`
9. `assistant.turn_end`
10. `system.message`
11. `user.message`
12. `assistant.turn_start`
13. `assistant.message`
14. `tool.execution_start`
15. `hook.start`
16. `hook.end`
17. `tool.execution_complete`
18. `assistant.turn_end`
19. `assistant.turn_start`
20. `assistant.message`
21. `assistant.turn_end`

## Event Flow

```
session.start
  └─ session.error (auth)
      └─ session.info (auth success)
          └─ session.info (MCP connected)
              └─ session.model_change (auto)
                  └─ system.message (full prompt + tools)
                      └─ user.message (with <system_reminder>)
                          └─ assistant.turn_start
                              └─ assistant.message (model: gpt-5-mini)
                                  ├─ tool.execution_start
                                  │   ├─ hook.start (postToolUse)
                                  │   └─ hook.end
                                  └─ tool.execution_complete
                              └─ assistant.turn_end
                          └─ assistant.turn_start (turn 2)
                              └─ assistant.message
                              └─ assistant.turn_end
```
