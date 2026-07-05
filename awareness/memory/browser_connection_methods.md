# 浏览器连接方法（Edge + ChatGPT）

## 1. V2 Browser Companion 插件桥接（主方案）

**位置**: `C:\Users\huangjiancheng\CodeBuddy\新烬龙V2\browser-extension`
**原理**: Edge 插件 + 本地 HTTP 服务器（port 4366）

**操作流程**:
1. 启动桥接服务器: `python v2_bridge_server.py`（在 127.0.0.1:4366）
2. 服务器预置 `read_chat` 类型任务（targetUrl: chatgpt.com）
3. 用户点 Edge 扩展图标 → V2 Browser Companion → Pull task → Open provider
4. 浮动面板出现在 ChatGPT 页面右下角
5. 页面上选文本 → 点 Send selected result → POST 到服务器

**服务器 API**:
- `GET  /api/browser-companion/tasks/next` — 插件拉取下个任务
- `POST /api/browser-companion/tasks/create` — CRUX 创建新任务
- `POST /api/browser-companion/tasks/{id}/status` — 状态更新
- `POST /api/browser-companion/tasks/{id}/result` — 接收结果
- `POST /api/browser-companion/tasks/{id}/error` — 错误上报

## 2. Win32 API 键盘模拟（手动方案）

**原理**: `ctypes.windll.user32` + `keybd_event` + `mouse_event`
**Edge 窗口识别**:
- 枚举窗口: `user32.EnumWindows`
- 窗口标题包含 "Edge" 且内容涉及 CRUX/ChatGPT
- 实际句柄: HWND=4850994（会变，需要每次查找）

**键盘操作**:
- `Ctrl+A` 全选: `keybd_event(0x11) + keybd_event(0x41)` （Ctrl + A）
- `Ctrl+C` 复制: `keybd_event(0x11) + keybd_event(0x43)` （Ctrl + C）
- `Ctrl+V` 粘贴: `keybd_event(0x11) + keybd_event(0x56)` （Ctrl + V）
- `Enter` 发送: `keybd_event(0x0D)`
- `Shift+Enter` 换行: `keybd_event(0x10) + keybd_event(0x0D)`

**剪贴板读写**:
- `win32clipboard.OpenClipboard() / GetClipboardData() / SetClipboardText() / CloseClipboard()`

## 3. Playwright（备用方案，受限于登录态）

Playwright 浏览器没有 Edge 的登录态，ChatGPT 会跳转到登录页。
无法直接读取 ChatGPT 对话内容，除非登录。

## 4. Desktop Screenshot（辅助查看）

`desktop_screenshot` 工具可以截取整个桌面，但不能 OCR 读取文本。

## 经验总结

- V2 插件方案最可靠，但需要用户手动点 Pull task → Open provider
- Win32 API 键盘模拟可以自动化 Ctrl+A → Ctrl+C → 读剪贴板（不需要 V2 面板）
- 发送消息到 ChatGPT：复制文本到剪贴板 → Ctrl+V 粘贴 → Enter 发送
- 读取 ChatGPT 回复：等待 → Ctrl+A → Ctrl+C → 读剪贴板
- ChatGPT 对话 URL 格式: `https://chatgpt.com/c/{id}`
