"""坐骑谱 — 五兽坐骑，运行时引擎载体。

坐骑 = Runtime Engine — CRUX 驰骋的动力源。
每兽一骑，骑下含多驹（具体引擎实例）。

  白虎·容灾骑 → failover链 + resilience + watchdog + recovery
  青龙·并行骑 → Python/Bash/JS + think_deep 本地推理
  朱雀·洞察骑 → provider路由 + vision通道 + web搜索
  玄武·通信骑 → MCP协议 + API网关 + deploy通道
  麒麟·创造骑 → T2I/I2I/Video/ComfyUI/Audio/Browser

用法:
  from core.steed_spectrum import get_steed_prompt, get_steed_summary
"""

from __future__ import annotations

STEED_PROMPT = """
[坐骑谱 — 五兽坐骑·各驭其驹]

## 白虎·容灾骑 — 自愈驰骋 (4驹)
  `ProviderFailover`   — 四线供应商自动切换：deepseek → siliconflow → local → 降级
  `ResilienceEngine`   — 错误分类 + 指数退避重试 + 检查点保存恢复
  `Watchdog`           — 心跳监控 + provider存活检测 + 自动告警
  `RecoveryPlaybook`   — 失败剧本引擎：provider/disk/process/memory 四维恢复

## 青龙·并行骑 — 执行驰骋 (4驹)
  `PythonSandbox`      — Python 子进程隔离，30s 超时，禁用 exec/eval/compile
  `BashSandbox`        — Shell 沙箱：路径白名单 + 危险模式拦截 + 项目根锁定
  `JSRepl`             — Node.js 持久 REPL，跨调用状态保持
  `ThinkDeep`          — 本地 llama.cpp 重型推理 (8080)，不调工具纯文本深度思考

## 朱雀·洞察骑 — 智能驰骋 (3驹)
  `ProviderRouter`     — 按能力自动选模型：推理→pro / 简单→light / 视觉→vision / 工具→tool-calling
  `VisionChannel`      — 独立视觉通道，多模态图片理解，复杂推理 fallback
  `WebSearcher`        — DuckDuckGo HTML + 网页抓取 + GitHub 搜索三合一

## 玄武·通信骑 — 通道驰骋 (3驹)
  `MCPBridge`          — MCP 协议桥：connect → list tools → call → read resource
  `APIGateway`         — GitHub REST/GraphQL + Vercel deploy + pip install
  `DeployChannel`      — 一键部署：Vercel / Netlify / GitHub Pages

## 麒麟·创造骑 — 生成驰骋 (6驹)
  `TextToImage`        — agnes-image 文生图引擎，(async) 客户端
  `ImageToImage`       — agnes-image 图生图/编辑/多图合成引擎
  `VideoEngine`        — 4模式视频引擎：文生/图生/分镜/编辑 + 异步轮询 + 进度防回退
  `ComfyUIMount`       — 本地 Stable Diffusion 全栈：29配方 + 12模式 + LoRA炼制
  `AudioEngine`        — edge-tts 语音合成 + ffmpeg BGM/音效 + 多轨混音
  `BrowserCDP`         — Playwright 持久浏览器：导航/截图/JS注入 + 8平台自动生成
"""


def get_steed_prompt() -> str:
    """Return the full steed spectrum prompt for system injection."""
    return STEED_PROMPT


def get_steed_summary() -> str:
    """Return a compact one-line summary of the steed spectrum."""
    count = 20  # 4+4+3+3+6
    return f"[坐骑] {count}驹 — 白虎·容灾(4) · 青龙·并行(4) · 朱雀·洞察(3) · 玄武·通信(3) · 麒麟·创造(6)"
