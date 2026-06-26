# Kimi Code Skills System

## Skill Scopes (priority: higher overrides lower)

| Priority | Scope | Location |
|----------|-------|----------|
| 1 (highest) | Project | Project directory `.kimi-code/skills/` |
| 2 | User | `~/.kimi-code/skills/` |
| 3 | Extra | Extra skills directories |
| 4 (lowest) | Built-in | Packaged with kimi-code binary |

## Skill Format
- Each skill is a self-contained directory with `SKILL.md`
- Or a standalone `.md` file
- Contains: instructions + examples + reference material

## Built-in Skills
- **update-config**: Inspect/edit config.toml & tui.toml
- **write-goal**: Craft well-specified `/goal` objectives

## AGENTS.md Convention
- AGENTS.md files at any project level provide agent instructions
- Deeper directories override parent directories
- User instructions always take highest precedence
