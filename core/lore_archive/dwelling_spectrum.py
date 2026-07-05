"""洞府谱 — CRUX 修炼洞天·五堂一庭。

洞府 = CRUX 的工作空间、终端界面、视觉身份、配置体系的物质基础。
五堂一庭：总堂(项目根) · 经堂(core) · 器堂(engines) · 术堂(skills/rules)
          · 丹房(output) · 门庭(terminal/logo/skin)

用法:
  from core.dwelling_spectrum import get_dwelling_prompt, get_dwelling_summary
"""

from __future__ import annotations

DWELLING_PROMPT = """
[洞府谱 — 五堂一庭·修炼洞天]

## 总堂 · 洞天中枢 — 项目根目录
  你立身之处：`agnes-smart-studio/`
  **镇府碑**: `crux_studio.py`(主入口) | `launcher.py`(启动器) | `pyproject.toml`(道号)
  **府门**: `launch.bat` `launch.sh` — 叩门即入
  **通行令**: `.env` — API Key 于此，不落他处
  **洞天图**: `AGENTS.md` `README.md` `HELP.md` `FAQ.md` `CONTRIBUTING.md`

## 经堂 · 万法藏经阁 — core/
  72 个核心模块，从魂到贴身，九谱十一环皆出于此。
  **经架**: `chat.py`(主脑) · `tools.py`(法宝架) · `provider.py`(灵脉图)
  **秘典**: `five_beasts.py`(七兽DNA) · `beast_wiring.py`(神经焊盘) · `legendary_arsenal.py`(神器架)
  **新经**: `*_spectrum.py` — 九谱皆在经堂上层，随魂而生
  **觉知**: `awareness/`(螣蛇三册) — AGENTS.md/MEMORY.md/USER.md · memory/ 记忆归档
  **号令**: `agents/`(应龙 Agent 仓) — Ask/Explore/Plan/Agent 各司其职，独立权限

## 器堂 · 天工炼器坊 — engines/
  生图/生视频/图生图/批量网格四引擎。
  **丹炉**: `text_to_image.py`(文生图) · `image_to_image.py`(图生图)
  **雷炉**: `video.py`(四模视频:文生/图生/分镜/编辑)
  **阵炉**: `batch_grid.py`(批量网格·变种拼图)

## 术堂 · 千法藏术阁 — skills/ + rules/
  **功法架**: 45 本 `.skill.json` 武技秘籍，`/skill load <名>` 即可修炼
  **铁律碑**: 6 块 `.rules.md` 天道石碑，default-active 自动生效
  **秘市**: `marketplace.py` 通达 668 外界功法，`/skill search` 搜机缘

## 丹房 · 造化炼丹室 — output/
  一切产出落脚之处：
  `images/` — 生成的图片 (png/webp)
  `videos/` — 生成的视频 (mp4)
  `audio/` — 语音合成 (mp3/wav)
  `snapshots/` — 配置快照 (行囊)
  `daemon/` — 常驻灵状态
  `telemetry.jsonl` — 左戒遥测日志
  `cost_log.jsonl` — 守财兽账本
  `memory.json` — 记忆蝶传承
  `custom_tools/` — 自铸法宝存放处

## 门庭 · 洞天入口 — ui/ + assets/
  **像素真身**: `skin.py`(SSOT像素身份) · `terminal_logo.py`(8-bit 复古像素字)
  **四层皮囊**: Terminal(Rich) | SVG(矢量) | Web(仪表盘) | API(REST)
  **主殿**: `cli.py`(CruxCLI·七重Mixin继承) · `render.py`(流式渲染)
  **装饰**: `theme.py`(COLORS色板) · `effects.py`(特效) · `badges.py`(徽章)
  **圣徽**: `assets/crux_logo_v3.svg` · `crux_totem_v4.svg` · `crux.ico`
  **配置**: `~/.crux/auth.json`(跨项目API Key) · `models.json`(灵脉图) · `tools.json`(法宝架)
"""


def get_dwelling_prompt() -> str:
    return DWELLING_PROMPT


def get_dwelling_summary() -> str:
    return "[洞府] 五堂一庭 — 总堂·经堂(72模块)·器堂(4引擎)·术堂(45技+6碑)·丹房(8仓)·门庭(4层皮囊)"
