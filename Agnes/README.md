# Agnes — Agnes AI 平台本地客户端

多模态 AI API 一键调用：**Chat · Vision · Image · Img2Img · Video**

## 安装

```bash
pip install requests
```

## 配置

```bash
# 设置 API Key (https://platform.agnes-ai.com/settings/apiKeys)
set AGNES_API_KEY=sk-your-key-here
```

或创建 `.env` 文件：`AGNES_API_KEY=sk-your-key-here`

## 命令行

```bash
# 对话
python -m agnes.cli chat "你好" -m agnes-2.0-flash
python -m agnes.cli chat --thinking   # 深度思考模式

# 图片对话
python -m agnes.cli vision "描述这张图" --image photo.jpg

# 文生图
python -m agnes.cli image "赛博朋克猫" --size 1024x1024 --save cat.png
python -m agnes.cli image "4K壁纸" --size 4096x4096

# 图生图
python -m agnes.cli img2img "变成水彩画风格" --image photo.jpg

# 文生视频
python -m agnes.cli video "海浪拍打礁石" --wait --save wave.mp4

# 图生视频
python -m agnes.cli video "让画面动起来" --image start.jpg --wait

# 查询视频状态
python -m agnes.cli video-status <video_id>

# 模型列表
python -m agnes.cli models

# 交互模式
python -m agnes.cli interactive
```

## Python API

```python
from agnes import AgnesClient

client = AgnesClient()

# Chat
reply = client.chat_text("你好")
reply = client.chat_text("分析这段代码", thinking=True)

# Vision (多模态)
desc = client.chat_with_image("图片里有什么？", "photo.jpg")

# Image
images = client.generate_image("一只猫", size="1024x1024")
path = client.generate_image_and_save("一只猫")

# Img2Img
images = client.generate_image("变动漫", image_urls=["photo.jpg"])

# Video
result = client.generate_video("海浪", wait=True)

# Models
for m in client.list_models():
    print(m["id"])
```

## 模型

| 模型 | 类型 | 亮点 |
|------|------|------|
| `agnes-2.0-flash` | Chat | 512K context · 多模态 · Tools · Thinking · 流式 |
| `agnes-1.5-flash` | Chat | 512K context · 基础对话 |
| `agnes-image-2.1-flash` | Image | 最大4K · 图生图 |
| `agnes-image-2.0-flash` | Image | 最大4K · 图生图 · 快速 |
| `agnes-video-v2.0` | Video | 文生视频 · 图生视频 |

## 图片尺寸

| 等级 | 尺寸 |
|------|------|
| 1K | 1024x768, 1024x1024, 768x1024 |
| 2K | 2048x2048, 2048x1536, 1536x2048 |
| 3K | 3072x3072, 3072x2304, 2304x3072 |
| 4K | 4096x4096, 4096x3072, 3072x4096 |
