# 智谱 GLM 免费模型接入手册

> API Key: 加密存储于 KeyVault `zhipu_api_key`
> Base URL: `https://open.bigmodel.cn/api/paas/v4`
> 接入日期: 2025-01-15

---

## 模型矩阵

### 对话模型

| 模型 ID | 上下文 | 特点 |
|---------|--------|------|
| `glm-4.7-flash` | 128K | 最新旗舰免费版，速度最快 |
| `glm-4-flash-250414` | 128K | 稳定版，`glm-4.7` 拥挤时降级用 |

### 视觉模型

| 模型 ID | 特点 | 用法 |
|---------|------|------|
| `glm-4v-flash` | 视觉理解 | 图片用 `image_url` 传 base64 |
| `glm-4.6v-flash` | 新一代视觉 | 同上，可能更精准 |
| `glm-4.1v-thinking-flash` | 视觉+深度推理 | 加 `thinking: {type: "enabled"}` 开启思维链 |

### 生成模型

| 模型 ID | 类型 | 调用方式 |
|---------|------|---------|
| `cogview-3-flash` | 文生图 | POST `/images/generations`，同步返回 URL |
| `cogvideox-flash` | 文生视频 | POST `/videos/generations` → GET `/async-result/{id}` 轮询 |

---

## API 端点

### 对话 (OpenAI 兼容)

```
POST /api/paas/v4/chat/completions
Authorization: Bearer {key}
Content-Type: application/json

{
    "model": "glm-4-flash-250414",
    "messages": [
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "你好"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
}
```

### 视觉

```json
{
    "model": "glm-4v-flash",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "图里有什么?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ]
    }]
}
```

### 深度推理 (Thinking)

```json
{
    "model": "glm-4.1v-thinking-flash",
    "messages": [...],
    "thinking": {"type": "enabled"}
}
```

响应含 `reasoning_content` 字段。

### 文生图

```
POST /api/paas/v4/images/generations
{"model": "cogview-3-flash", "prompt": "描述"}

→ {"data": [{"url": "https://..."}]}
```

### 文生视频

```
1. POST /api/paas/v4/videos/generations
   {"model": "cogvideox-flash", "prompt": "描述"}
   → {"id": "task_xxx", "task_status": "PROCESSING"}

2. GET /api/paas/v4/async-result/{task_id}
   → {"task_status": "SUCCESS", "video_result": [{"url": "..."}]}
```

---

## 调用限制

- **免费额度**: 每模型有 QPS 和日调用量限制
- **并发**: `glm-4.6v-flash` / `glm-4.7-flash` 高峰期可能返回 429
- **超时**: 直连有时读超时，建议 timeout=20s

## 故障转移链

```
deepseek → local(Qwen3.6-27B) → zhipu(glm-4-flash-250414) → codebuddy
```

智谱位于第三层。glm-4.7-flash 不可用时自动降级到 glm-4-flash-250414。

## 已注册到 models.json

所有 7 个免费模型已就绪，provider.py 通过标准 OpenAI 兼容路径调用。
