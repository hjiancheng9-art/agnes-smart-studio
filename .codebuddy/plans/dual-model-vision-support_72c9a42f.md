---
name: dual-model-vision-support
overview: 为 ChatSession 增加独立视觉客户端，使 /code 模式可以使用 DeepSeek 主聊 + Agnes light 处理图片理解，双模型并行。
todos:
  - id: add-vision-constant
    content: 在 core/config.py 新增 AGNES_VISION_MODEL 常量
    status: completed
  - id: refactor-chat-session
    content: 改造 core/chat.py：ChatSession 增加 vision_client/vision_model 字段，send_stream 使用视觉客户端路由，toggle_code_mode 解耦
    status: completed
    dependencies:
      - add-vision-constant
  - id: adapt-cli-dual-client
    content: 改造 ui/cli.py：AgnesCLI 创建 vision_client，_chat 传递视觉客户端，_chat_vision 取消门禁，_chat_switch_model 支持 raw ID，provider switch 保持视觉客户端独立
    status: completed
    dependencies:
      - refactor-chat-session
---

## 用户需求

在聊天 `/code` 模式下，主对话使用 DeepSeek (deepseek-chat) 进行代码问答，同时保留 Agnes 1.5-flash 的图片理解能力。切换模型供应商后主聊天走新供应商，但视觉能力始终可用。

## 核心功能

- **双客户端分离**：主对话客户端跟随 `/provider switch` 切换（DeepSeek/Kimi/Agnes），视觉客户端始终保持 Agnes 供应商
- **/code 模式解耦**：不再强制绑定 agnes-2.0-flash，允许使用当前供应商模型进行代码对话
- **/vision 命令通用化**：取消模型门禁，在任何主模型下都能用 Agnes light 识别图片
- **send_stream 视觉路由**：传入 image_url 时自动走视觉客户端，不依赖主模型 ID 判断
- **/model 命令扩展**：支持 raw model ID 直接切换（如 `/model deepseek-chat`），不再仅限 light/pro 别名

## 技术选型

- 语言：Python 3.10+
- 现有依赖：httpx、rich
- 不引入新依赖

## 实现方案

### 架构变更：单客户端 → 双客户端

```
┌─────────────────────────────────────────────────┐
│                  ChatSession                      │
│                                                   │
│  self.client ─────────► DeepSeek/Kimi/Agnes       │
│  (主对话，跟随 /provider switch)                   │
│                                                   │
│  self.vision_client ──► AgnesClient(agnes-ai)     │
│  (视觉能力，始终指向 Agnes API)                     │
│                                                   │
│  self.vision_model = "agnes-1.5-flash"            │
│  self.model = 当前供应商模型                        │
└─────────────────────────────────────────────────┘
```

### 关键决策

1. **视觉客户端独立构造**：`AgnesCLI.__init__` 中显式用 `AgnesClient(api_key=AGNES_API_KEY, base_url=AGNES_BASE_URL)` 创建，不依赖 SETTINGS 默认值，确保 `/provider switch` 不会误改视觉客户端。

2. **send_stream 路由策略**：检测到 `image_url` 时，直接走 `self.vision_client.chat_multimodal(model=self.vision_model)`，不判断 `self.model` 类型。无 image_url 时走正常流式路径（主 client）。

3. **toggle_code_mode 解耦**：去掉 `self.model = "agnes-2.0-flash"` 硬编码，仅设置 `code_mode` 标志 + 替换 system prompt。模型保持不变。

4. **_chat_vision 门禁移除**：不再检查 `session.model != "agnes-1.5-flash"`，改为直接使用 `session.vision_client.chat_multimodal()`。结果照常写入 `session.messages` 便于追问。

5. **/model 命令扩展**：MODEL_ALIASES 保留向后兼容，同时支持任意 model ID 直接赋值。

6. **向后兼容**：ChatSession 的 `vision_client` 参数默认 `None`，此时退化为 `self.client`（主 client），与当前行为一致。

### 性能与可靠性

- 视觉客户端仅在首次访问时创建，复用同一 http session
- `_chat_vision` 走整块返回（非流式），图片理解响应时间由 Agnes API 决定
- `/provider switch` 时关闭旧主 client、创建新主 client，视觉 client 不受影响
- 视觉客户端异常不影响主对话，错误信息透传给用户

### 改动范围

仅改 3 个文件，不涉及 models.json、brain.py 或其他模块。