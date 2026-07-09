# CRUX Studio - 常见问题 (FAQ)

## 编程助手

### ❓ 这个工具有编程能力吗？
有。聊天模式输入 `/code` 即可切换到**代码助手模式**（自动切换 pro 模型 + 开启 thinking）：
- 支持 Python、JavaScript、Go、Rust、Java、C/C++ 等
- 输出完整可运行代码（带语言标注）
- 分步骤讲解：分析 → 方案 → 代码 → 说明

### ❓ 代码模式 vs 普通聊天模式？
| | 代码模式 | 聊天模式 |
|---|---------|---------|
| 系统提示 | 资深全栈工程师 | 通用助手 |
| Thinking | 自动开启 | 需手动 /thinking |
| 模型 | 强制 pro | 可切换 light/pro |
| 生图/视频 | 不可自动触发 | pro 模型可自动触发 |

---

## 视频相关

### ❓ 视频生成排队超过 5 分钟？
**必须用 video_id 查询，不要用 task_id！** 使用 task_id 会导致排队异常延长。
- ✅ 正确：`crux query VIDEO_ID`
- ❌ 错误：使用 task_id 查询

### ❓ 如何调整视频长度？
视频长度由 `num_frames`（帧数）和 `frame_rate`（帧率）决定：**秒数 = num_frames / frame_rate**
- 交互菜单生成视频时会弹出时长选择（81~441 帧 @24fps）
- 命令行模式默认 121 帧/5 秒
- 帧数必须为 `8n+1`（81, 121, 161, 201, 241, 281, 321, 361, 401, 441）

### ❓ 视频仅提交不等待？
所有视频生成菜单都会询问"仅提交(不等待)?"，选"是"则提交后立即返回 video_id，稍后用 `--video-id` 查询。

### ❓ 如何查询视频状态？
```bash
crux query VIDEO_ID
# 或
crux query VIDEO_ID --timeout 60  # 限时等待
```

---

## 聊天模式

### ❓ 如何让 AI 自动生图/视频？
- 切换到 pro 模型：`/model pro`（agnes-2.0-flash）
- 说"帮我画一只猫"，AI 会自动调用生图工具
- light 模型（agnes-1.5-flash）不支持自动生成，需用 `/img` `/video` 命令

### ❓ 如何开启深度思考（thinking）？
聊天模式下输入 `/thinking` 切换开关（仅 pro 模型生效）。开启后模型会输出推理过程。

### ❓ 聊天模式支持图生图吗？
支持。`/img` 和 `/video` 命令可传入图片路径：
```
/img C:\photo.png 把这图变成水墨画风格
/video C:\photo.png 让图中的人动起来
```

### ❓ 聊天模式 vs 交互菜单有什么区别？
| | 聊天模式 | 交互菜单 |
|---|---------|---------|
| 启动 | `-c` | 默认 |
| 风格 | 自然语言对话 | 分步菜单选择 |
| 自动生图 | pro 模型支持 | 手动选功能 |
| 图片输入 | `/img` + 路径 | 图生图菜单 |

---

## 图片生成

### ❓ 图生图报 400 错误？
图片必须通过 `extra_body.image` 传入，不能放在请求顶层。如果你用代码调用，确保 `image` 字段在 `extra_body` 内。

### ❓ 提示词触发了内容安全过滤？
说明提示词或增强后的 prompt 含有被拦截的关键词。尝试用更中性的词汇替换攻击性描述，或关闭 Prompt 增强。

### ❓ Prompt 增强有用吗？
增强会调用 LLM 将简短描述扩展为结构化的专业提示词（主体/场景/光照/构图/风格等 10 段结构），画质明显提升。可通过 `--no-enhance` 关闭。

---

## 配置与安装

### ❓ API Key 在哪获取？
https://platform.agnes-ai.com 生成，粘贴到 `.env` 文件：
```
CRUX_API_KEY=sk-xxxxx
CRUX_BASE_URL=https://apihub.agnes-ai.com/v1
```

### ❓ 免费额度是多少？
RPM ≤20，所有模型永久免费。

### ❓ 支持哪些模型？
| 模型 | 用途 |
|------|------|
| `agnes-1.5-flash` | 对话 + 多模态图片理解 |
| `agnes-2.0-flash` | 对话 + 工具调用/深度思考 |
| `agnes-image-2.1-flash` | 图片生成 |
| `agnes-video-v2.0` | 视频生成 |

### ❓ 429 Too Many Requests？
RPM 超限（20 次/分钟），降低请求频率或等待重试。

### ❓ 启动报错"未找到 Python"？
安装 Python 3.10+，勾选"Add Python to PATH"。然后运行：
```bash
pip install -r requirements.txt
```

### ❓ 如何创建桌面快捷方式？
运行 `python launcher.py` 进入交互菜单，或直接 `python crux_studio.py -c` 启动聊天。
