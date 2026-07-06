# Edge Browser 自动化引擎
## Description
通过 Playwright (msedge channel) 控制 Edge 浏览器。支持导航、截图、填表、点击、提取文本、执行 JS。每次操作独立会话，零残留，零泄漏。

## Files
- `edge_engine.py` — 核心引擎（推荐直接 import 使用）
- `edge_connect.py` — 旧版（兼容保留）

## Python API
```python
from edge_engine import EdgeEngine

async with EdgeEngine() as engine:
    # 导航
    await engine.goto("https://www.baidu.com")
    
    # 截图 → output/ 目录
    await engine.screenshot("output/mypage.png")
    
    # 填表 + 点击
    await engine.fill("input[name=wd]", "搜索关键词")
    await engine.press("Enter")
    
    # 提取内容
    title = await engine.get_text("h3")       # {"text": "..."} 或 {"texts": [...]}
    links = await engine.get_links()           # {"links": [{"text":"...", "href":"..."}]}
    
    # 执行 JS
    await engine.evaluate("document.title")
```

## CLI 单命令模式
```bash
python edge_engine.py goto <url>
python edge_engine.py screenshot [path]
python edge_engine.py fill <selector> <text>
python edge_engine.py click <selector>
python edge_engine.py press <key>
python edge_engine.py text [selector]
python edge_engine.py links
python edge_engine.py eval <js>
```

## 注意事项
1. **Headless 模式** — 默认不显示窗口，截图可看结果
2. **网络超时** — 默认 30s，沙箱环境国内站点可能超时，推荐用 example.com 或先检查可达性
3. **自动清理** — 每次 `__aexit__` 自动关闭浏览器，零残留
4. **Selector 策略** — 优先用 `input[name=wd]` / `#su` / `h3` 等稳定选择器，避免动态 class
5. **等待策略** — `goto` 用 `domcontentloaded` 而非 `load`，更快；后续操作前可 `await asyncio.sleep(1)`

## Metadata
- created_at: 1783314000
- category: automation
- tags: edge, browser, playwright, automation
