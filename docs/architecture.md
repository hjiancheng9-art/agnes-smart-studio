# 架构设计

```
入口层    agnes_studio.py (CLI参数) / launcher.py (图形菜单) / launch.bat
   ↓
UI层     ui/cli.py (交互+聊天) / ui/display.py (渲染)
   ↓
会话层   core/chat.py (多轮+tool calling) / core/agent.py (计划+子智能体)
   ↓
智能层   core/brain.py (Prompt增强+知识注入) / core/skills.py (技能管理)
   ↓
工具层   core/tools.py (插件注册) / tools.json (外部工具)
   ↓
引擎层   engines/text_to_image.py / image_to_image.py / video.py
   ↓
客户端   core/client.py (API+重试+流式)
   ↓
API     Agnes AI / DeepSeek / Kimi (通过 models.json 切换)
```

## 三条数据流

### 生图/视频流
用户输入 → brain.enhance() → engine.generate() → client.create_image/video() → 展示

### 聊天流
用户消息 → chat_stream() → LLM 响应 → 如有 tool_calls → _dispatch_tool() → 结果喂回 → 二次响应

### 智能体流
/agent 加载 tools.json → LLM 自动选择工具 → ToolRegistry.execute() → 结果 → LLM 总结

## 数据存储
- `output/images/` `output/videos/` — 生成结果
- `output/history.json` — 生成记录+评分
- `output/memory.json` — 偏好学习+进化库
- `output/projects/` — 项目独立会话
- `skills/` `tools.json` `models.json` — 配置
