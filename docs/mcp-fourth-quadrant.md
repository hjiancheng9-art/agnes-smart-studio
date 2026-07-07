# 四象闭环：让 codex / claude / codebuddy 调用 CRUX 生成能力

## 概述

CRUX 通过 `crux mcp-serve` 子命令暴露 **MCP (Model Context Protocol) Server**，
成为与 codex (OpenAI) / claude (Anthropic) / codebuddy 对等的"第四象"。

三象负责 **code**，CRUX 负责 **create**：
- 文生图 / 图生图 / 视频生成（含 LLM prompt 增强）
- 71 个全量工具（pipeline / comfyui / notebook / audio / tools.json）
- output/ 产物资源浏览

> **一行接入**：`claude mcp add crux -e CRUX_API_KEY=sk-xxx -- crux mcp-serve`

---

## 前置条件

1. **CRUX API Key** — 以下任一方式已配置：
   - 环境变量 `CRUX_API_KEY` 已设
   - 已运行 `crux init` 写入 `~/.crux/auth.json`
2. **crux 命令可用** — `crux` 已在 PATH（`pip install -e .` 后自动注册）

```bash
# 验证
crux version          # → CRUX Studio v6.0.0
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | crux mcp-serve
# → {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...}}
```

---

## 接入方式

### Claude Code

```bash
# 推荐：环境变量注入 API Key
claude mcp add crux -e CRUX_API_KEY=sk-your-key -- crux mcp-serve

# 若系统已有 CRUX_API_KEY 环境变量，可省略 -e
claude mcp add crux -- crux mcp-serve

# 验证
claude mcp list
# → crux  stdio  crux mcp-serve
```

**使用**（在 claude 会话里）：
```
> 用 crux 的 generate_image 工具画一张赛博朋克风格的中国龙
> 调用 crux.generate_video 生成一个 5 秒的海浪动画
```

Claude Code 会通过 MCP 自动发现 CRUX 的工具集（71 个），tool calling 时
直接走 `crux mcp-serve` → `ChatSession._dispatch_tool_impl` → 引擎生成。

---

### Codex (OpenAI)

```bash
# stdio 模式，通过 --env 注入 API Key
codex mcp add crux --env CRUX_API_KEY=sk-your-key -- crux mcp-serve

# 或写入 ~/.codex/config.toml 长期生效：
# [mcp_servers.crux]
# command = "crux"
# args = ["mcp-serve"]
# env = { CRUX_API_KEY = "sk-your-key" }

# 验证
codex mcp list
```

**使用**（在 codex 会话里）：
```
> 用 mcp 工具 generate_image 为这个架构生成一张示意图
```

Codex 通过 `tools/list` 发现 CRUX 工具，`tools/call` 触发生成。

---

### CodeBuddy

```bash
# 与 claude 语法一致
codebuddy mcp add crux -e CRUX_API_KEY=sk-your-key -- crux mcp-serve

# 验证
codebuddy mcp list
```

**使用**（在 codebuddy 会话里）：
```
> 调用 crux 的 generate_image 工具
```

---

## 协议规格

| 项目 | 值 |
|---|---|
| 协议 | JSON-RPC 2.0 |
| 传输 | stdio（stdin 请求 / stdout 响应 / stderr 日志） |
| 分帧 | newline-delimited JSON（每条消息一行 `\n`） |
| 编码 | UTF-8 |
| MCP 版本 | `2024-11-05` |
| 超时 | 同步一问一答，建议 client 侧设 60s+（视频生成可到 300s） |

### 支持的 MCP 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，返回 `protocolVersion` + `capabilities` + `serverInfo` |
| `notifications/initialized` | 通知（静默接受，不回响应） |
| `tools/list` | 返回全量 71 个工具，MCP shape `{name, description, inputSchema}` |
| `tools/call` | 统一走 `ChatSession._dispatch_tool_impl`，覆盖 BUILTIN + registry 全部工具 |
| `resources/list` | 列出 `output/images/` `output/videos/` 下的产物（最多 100 条） |
| `resources/read` | 按 `file://` URI 读取产物（图片返回 base64 blob，视频返回路径文本） |

### `tools/call` 参数

```json
{
  "name": "generate_image",
  "arguments": {
    "prompt": "一只赛博朋克风格的猫",
    "image_url": ""           // 可选，参考图片
  }
}
```

### `tools/call` 返回

**成功（生图）**：
```json
{
  "content": [
    { "type": "text", "text": "图片已生成并保存: .../t2i_20260623.png" },
    { "type": "image", "data": "<base64>", "mimeType": "image/png" },
    { "type": "text", "text": "{\"local_path\":\"...\",\"url\":\"...\",\"model\":\"agnes-image-2.1-flash\"}" }
  ],
  "isError": false
}
```

**成功（生视频）**：
```json
{
  "content": [
    { "type": "text", "text": "{\"local_path\":\".../vid.mp4\",\"video_id\":\"v1\",\"url\":\"...\"}" }
  ],
  "isError": false
}
```

**超时（视频）**：
```json
{
  "content": [
    { "type": "text", "text": "[video timeout] progress=45%, video_id=v9 — poll later..." }
  ],
  "isError": false
}
```

**高风险工具被拒**：
```json
{
  "content": [
    { "type": "text", "text": "Tool 'git_push' requires interactive confirmation (high-risk). MCP mode refuses high-risk tools." }
  ],
  "isError": true
}
```

---

## 暴露的核心工具（三象最爱用的）

| 工具名 | 说明 | 关键参数 |
|---|---|---|
| `generate_image` | 文生图 / 图生图（含 LLM prompt 增强） | `prompt`(必填), `image_url`(可选) |
| `generate_video` | 文生视频 / 图生视频（含 LLM prompt 增强） | `prompt`(必填), `image_url`(可选) |
| `multi_agent` | 多智能体并行协调 | `goal`(必填) |
| `showrun_decompose` | 创意分镜拆解 | `goal`(必填), `style` |
| `save_project_manifest` | 保存项目资产清单 | `project_name`, `assets` |
| `extract_video_keyframes` | 视频关键帧提取 | `video_path` |
| `comfyui_submit_workflow` | ComfyUI 自定义工作流提交 | `workflow_json`, `wait` |

完整 71 个工具列表：启动 `crux mcp-serve` 后发送 `tools/list` 查看实时列表。

---

## 故障排查

### `crux mcp-serve` 无响应

```bash
# 1. 确认 API Key 可用
crux version                              # 若报 CRUX_API_KEY 未设置 → crux init

# 2. 手动测试 server
python -c "
import subprocess,json
p=subprocess.Popen(['crux','mcp-serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE,text=True,encoding='utf-8')
req=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})+'\n'
out,err=p.communicate(req,timeout=30)
print(out)
print(err)
"
```

### 三象报 `method not found` 或 `tool not found`

- 确认三象的 MCP client 发送 `initialize` 后再发 `tools/list`（握手必须先完成）
- 确认 `crux mcp-serve` 进程没有因为缺 API Key 而提前退出（查 stderr 日志）

### 三象调 `generate_image` 无反应

- 视频生成可能耗时 30-300 秒（取决于内容复杂度），三象的 MCP client 超时需设够
- 文生图通常 5-15 秒

### Windows 换行问题

`crux mcp-serve` 已内置 `stdout.reconfigure(newline="\n")`。
若三象的 stdio transport 仍有解析问题，检查三象是否使用 Content-Length framing
（CRUX 用 newline-delimited，不是 LSP 的 `Content-Length: N\r\n\r\n{json}`）。

---

## 架构

```
三象 (claude / codex / codebuddy)
    │
    │  MCP Client (stdio transport, newline-delimited JSON)
    │
    ▼
crux mcp-serve          ← core/mcp_server.py (JSON-RPC 2.0 主循环)
    │
    ├─ initialize / tools/list / resources/list / resources/read
    │
    └─ tools/call
         │
         ▼
    ChatSession._dispatch_tool_impl     ← core/chat.py:662 (统一调度)
         │
         ├─ generate_image / generate_video / multi_agent  (BUILTIN, 含 LLM prompt 增强)
         │
         └─ ToolRegistry.execute(...)   (pipeline / comfyui / notebook / audio / tools.json)
              │
              ├─ core/pipeline_tools.py
              ├─ core/comfyui_tools.py
              ├─ core/browser_tools.py
              ├─ core/notebook.py
              └─ tools.json → shell / http / python 执行器
```

**对称性**：`core/mcp_server.py` 与 `core/mcp_client.py` 完全镜像——
同一个 `2024-11-05` 协议、同一种 newline 分帧、同一套 JSON-RPC 2.0 envelope。
区别只在方向：client 连别人的 server，server 让别人连自己。
