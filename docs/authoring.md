# 技能与工具写作规范

> 参考 OpenAI harness-engineering 实践，渐进式披露原则。

## Skill 文件 (.skill.json)

必填字段：`name`, `description`, `prompt`

```json
{
  "name": "my-skill",
  "description": "使用场景描述 (Use when...)",
  "version": "1.0",
  "icon": "🔧",
  "prompt": "激活 XX 模式。规则：\n1. ...\n2. ..."
}
```

### 描写规范
- `description`: 包含触发短语 Use when / 用于 / 当...时使用
- `prompt`: 不超过 8KB，超过的部分放 references/
- 分隔用 `\n`，不用 markdown 代码块

## 工具配置 (tools.json)

三种类型：`shell` / `http` / `python`

```json
{
  "name": "tool_name",
  "type": "shell",
  "description": "工具描述",
  "command": "执行命令，参数用 {param} 占位",
  "parameters": {
    "param": {"type": "string", "description": "...", "required": true}
  }
}
```

### 规范
- shell 命令须幂等或无副作用的读操作
- http 工具 URL 须是公开可访问地址
- python 工具 function 用 module.function 格式
- 危险操作加确认机制

## 描述触发器
- 技能 description 包含触发词提高自动匹配率
- 工具 description 清晰描述输入输出，AI 才能正确调用
