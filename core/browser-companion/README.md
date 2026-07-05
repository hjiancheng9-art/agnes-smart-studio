# browser-companion

CRUX Studio 的浏览器伴侣扩展，用于桥接 TUI 与 Web 服务（ChatGPT、Gemini 等）。

## 结构

```
core/browser-companion/
├── extension/              # Manifest V3 Chrome/Edge 扩展
│   ├── manifest.json
│   ├── background.js       # Service worker — 轮询任务 + 通信
│   ├── content-script.js   # 注入页面的浮动面板
│   ├── providers/          # 各平台适配器
│   │   ├── chatgpt.js
│   │   ├── gemini.js
│   │   ├── opal.js / flow.js / kling.js / jimeng.js / runway.js / luma.js
│   └── popup.html / popup.js / styles.css
├── bridge_server.py        # 本地 HTTP 服务器 (port 4366)
└── README.md
```

## 工作流

1. 启动 bridge server: `python core/browser-companion/bridge_server.py`
2. 在 CRUX Studio 内请求 Web 任务（如 `/chatgpt`、`/gemini`）
3. 浏览器扩展 Pull task → Open provider → 浮动面板
4. 用户手动提交 prompt，选中结果发回 V2

## 安装

Edge: `edge://extensions` → 开发者模式 → 加载已解压的扩展 → 选择 `core/browser-companion/extension/`
