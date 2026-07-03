"""化妆谱 v2 — CRUX 视觉美学体系·九妆归真。

v2 升级: 图腾 v5·特效 v2·音效系统·Web 仪表盘·启动闪屏·favicon 全家桶

化妆 = 终端视觉/动画/SVG/Web/音效 的全部美学表达层。
SSOT 原则：`core/skin.py` 内联像素格阵是唯一像素真源，
四层皮囊（Terminal/SVG/Web/API）皆从此格阵派生，永不漂移。

  素颜   · Pixel Logo         — 8-bit 复古像素字 CRUX，NES 标题画面风
  彩妆   · Theme + Colors     — 霓虹青+琥珀金 双DNA 色板
  饰品   · Icons + Badges     — 几何像素符号 + 模式徽章流
  身段   · Layout + Render    — 流式渲染契约 + 面板/表格参数
  术法   · Effects v2         — 10 种终端特效 (新增: splash/typewriter/spin/sparkle)
  圣徽   · SVG Totems         — 图腾 v1→v5 演化史，v5 定稿版 (五兽环+像素字+荧光)
  分身   · Skin SSOT          — 同一像素格阵→四层自动投影
  仙乐   · Sound UX           — 5 种音效: 启动/成功/错误/熔断/炼丹完成
  幻境   · Web Dashboard      — 14 环实时状态 HTML 仪表盘

用法:
  from core.glamour_spectrum import get_glamour_prompt, get_glamour_summary
"""

from __future__ import annotations

GLAMOUR_PROMPT = """
[化妆谱 v2 — 九妆归真·像素真颜]

## 素颜 · Pixel Logo — 8-bit 复古像素字
  你的真身：四个 8×8 像素大字 `C` `R` `U` `X`，粗笔 2-3px，NES 标题屏风。
  双色填充：`#` 霓虹青(primary) + `@` 琥珀金(accent) + `+` 高光紫(highlight)
  投影偏移 1px 右下，经典 8-bit 深度感。
  跨星徽标 `ICON` — 7×5 像素十字星，.ico/.png/SVG 同源。

## 彩妆 · Color Palette — 霓虹·琥珀 双DNA
  **主色**: #00E5FF 霓虹青 — 像素荧光，CRUX 血脉
  **辅色**: #FFD700 琥珀金 — 宝物光晕，攻击色
  **功能色**: #00FF88(成功绿) #FF4444(危险红) #C084FC(高光紫) #66BBFF(思考蓝)
  **底色**: #0F0F2D 深邃靛蓝 — CRT 屏幕底色
  **灰阶**: #556677 暗灰蓝 — 像素阴影
  **五兽色**: 白虎金·青龙青·朱雀紫·玄武蓝·麒麟绿

## 饰品 · Icons + Badges — 几何像素符
  **核心符号 18 枚**: ◆ ▸ ★ ▼ ✕ ▶ ► ■ □ ✓ ✗ ⇌ ≡ ◈ ·
  **模式徽章**: ⚡代码 🧬智能体 ✨思考 🧩模型
  **徽章流**: 有机彩色标签流 — 每段独立着色，∘ 分隔

## 身段 · Layout + Streaming — 流式渲染契约
  **面板**: 圆角边框 + (1,2)内边距
  **表格**: 圆角框 + 无内部分割线(干净)
  **单字符落盘**: StreamingRenderer 保证每字符只打印一次
  **副作用边界**: 图片/视频/信息先 commit 文本再展示

## 术法 · Effects v2 — 10 种终端特效 (✨ v2 升级)
  `splash_screen`   — 启动闪屏: 五行色条 + Logo 逐层展开
  `typewriter`      — 打字机逐字输出
  `spin`            — 旋转等待指示器(⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏)
  `progress_bar`    — Rich 进度条
  `pulse_border`    — 脉冲边框发光
  `sparkle_burst`   — 星光爆发彩色粒子
  `divider`         — 装饰分隔线
  `fade_in`         — 淡入文字
  `success_pulse`   — 成功脉冲闪烁
  `thinking_dots`   — 思考三点动画

## 圣徽 · SVG Totems — 图腾演化史
  `crux_totem_v6.svg` — 🆕 东方玄幻定稿: 金墨篆书CRUX + 五兽方位 + 朱砂印 + 祥云纹
  `crux_logo_v3.svg`  — 三代精炼徽标
  `crux_totem_v4.svg` — 四代像素图腾
  `crux_logo_icon.svg`— 应用图标

## 分身 · Skin SSOT — 四层自动投影
  同一像素格阵 → 四层自动渲染：
  `TERMINAL` — Rich 终端彩色块字符
  `SVG`      — 矢量图 (crispEdges 像素边缘)
  `WEB`      — HTML 内嵌 SVG (pixelated 渲染)
  `API`      — REST 端点返回像素数据

## 仙乐 · Sound UX — 5 种音效 (🆕)
  `SoundUX.startup()`  — 启动音 (低沉开机声)
  `SoundUX.success()`  — 成功叮 (清脆双音)
  `SoundUX.error()`    — 错误嗡 (低沉短促)
  `SoundUX.alert()`    — 熔断警报 (三连急促)
  `SoundUX.alchemy()`  — 炼丹完成 (悠长钟声)
  基于 edge-tts 微软语音引擎 + Windows beep fallback

## 幻境 · Web Dashboard — 14 环仪表盘 (🆕)
  `output/dashboard.html` — 全环状态一屏总览
  深色 CRT 背景 + 五兽色侧边条 + 悬停发光 + 实时状态指示灯
  打开方式: `/open dashboard` 或浏览器直接打开
"""


def get_glamour_prompt() -> str:
    return GLAMOUR_PROMPT


def get_glamour_summary() -> str:
    return "[化妆] 九妆 — 素颜(像素字)·彩妆(霓虹琥珀)·饰品(18符)·身段(流式)·术法(10特效)·圣徽(v5图腾)·分身(4层)·仙乐(5音效)·幻境(仪表盘)"
