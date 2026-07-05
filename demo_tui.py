#!/usr/bin/env python3
"""
CRUX 终端美学 — 交互演示

运行: python demo_tui.py
"""

import os
import sys
import time

# 确保脚本所在目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tui_art import Badge, C, divider, echo, panel, progress_bar, status_bar, toolchain_display, welcome_screen


# ─── 清屏 ─────────────────────────────────────────────
def clear():
    os.system("cls" if os.name == "nt" else "clear")

# ─── 定帧动画 ─────────────────────────────────────────
def typewriter(text: str, delay: float = 0.03):
    for ch in text:
        print(ch, end="", flush=True)
        time.sleep(delay)
    print()

# ─── 场景1: 启动 ──────────────────────────────────────
def scene_boot():
    clear()

    # 逐字启动信息
    boot_lines = [
        (C.CRUX_R,  "[ BOOT ] ▸ 七兽序列加载中..."),
        (C.CRUX_O,  "[ BOOT ] ▸ 白虎之骨 · ✅"),
        (C.CRUX_G,  "[ BOOT ] ▸ 青龙之脉 · ✅"),
        (C.CRUX_R,  "[ BOOT ] ▸ 朱雀之眼 · ✅"),
        (C.CRUX_C,  "[ BOOT ] ▸ 玄武之甲 · ✅"),
        (C.CRUX_P,  "[ BOOT ] ▸ 麒麟之手 · ✅"),
        (C.CRUX_Y,  "[ BOOT ] ▸ 螣蛇之忆 · ✅"),
        (C.CRUX_O,  "[ BOOT ] ▸ 应龙之令 · ✅"),
        (C.GREEN,   "[ BOOT ] ▸ 七兽融合 · 魂魄交融"),
    ]
    for clr, line in boot_lines:
        typewriter(f"{clr}{line}{C.RESET}")
        time.sleep(0.1)
    time.sleep(0.3)

    clear()
    welcome_screen(project="agnes-smart-studio")
    time.sleep(1.5)

# ─── 场景2: 徽章橱窗 ─────────────────────────────────
def scene_badges():
    """Badge橱窗 — 展示6种Badge风格 + 动画Badge"""
    clear()
    from tui_art import BadgeStyle, C, render_badge

    print(f"\n{C.WHITE}{C.BOLD}  ✦ BADGE 系 统 橱 窗 ✦{C.RESET}\n")

    # 逐个展示 Badge 风格
    for label, color, icon, desc in [
        ("平时如刀", C.CRUX_C, "⚡", "hot path 热路径"),
        ("白虎炼骨", C.CRUX_R, "🐯", "bordered 精致"),
        ("青龙通脉", C.CRUX_G, "🐉", "glow 发光"),
        ("朱雀开眼", C.CRUX_B, "🦅", "tagged 标签"),
        ("麒麟锻造", C.CRUX_O, "⚒", "icon 图标"),
    ]:
        print(f"  {C.DIM}{desc}{C.RESET}")
        badge = render_badge(label, style=BadgeStyle.MINIMAL, color=color, icon=icon)
        for line in badge.split("\n"):
            if line.strip():
                print(f"    {line}")
        time.sleep(0.4)

    # 动画 Badge 演示
    print(f"\n  {C.DIM}动画 Badge 演示 (pulse){C.RESET}\n")
    from ui.widgets_v2 import AnimatedBadge
    badge = AnimatedBadge("应龙号令", color=C.CRUX_C, icon="🐲", anim="pulse")
    for _ in range(6):
        print(f"\r    {badge.next()}", end="", flush=True)
        time.sleep(0.3)
    print("\n")

    input(f"{C.DIM}按 Enter 继续...{C.RESET}")
# ─── 场景3: 彩虹字体 ─────────────────────────────────
def scene_fonts():
    divider("═", C.CRUX_C, "七兽字体 · 全字体巡礼")
    time.sleep(0.3)

    font_demo = [
        ("hero",    "CRUX",     C.CRUX_R),
        ("sub",     "STUDIO",   C.CRUX_G),
        ("cyber",   "CYBER",    C.CRUX_P),
        ("chunk",   "BEAST",    C.CRUX_O),
        ("future",  "DREAM",    C.CRUX_Y),
        ("minimal", "AGNES",    C.CRUX_B),
    ]
    for key, word, clr in font_demo:
        print(f"  {C.DIM}[font: {key}]{C.RESET}")
        echo(word, font=key, color=clr)
        time.sleep(0.2)
    time.sleep(1.0)

# ─── 场景4: 状态面板 ─────────────────────────────────
def scene_panels():
    divider("═", C.CRUX_O, "系统面板 · 状态监控")
    time.sleep(0.3)

    panel("⚙  系统负载",
          f"  CPU:  {progress_bar(23, 30, color=C.CRUX_G)}\n"
          f"  MEM:  {progress_bar(67, 30, color=C.CRUX_Y)}\n"
          f"  DISK: {progress_bar(42, 30, color=C.CRUX_B)}\n"
          f"  NET:  {progress_bar(88, 30, color=C.CRUX_R)}",
          C.CRUX_C, 52)
    time.sleep(0.5)

    panel("🗡  七兽武装状态",
          f"  {C.CRUX_B}白虎{C.RESET}  骨骼架构 {Badge.inline('ACTIVE','ok')}      {C.CRUX_G}青龙{C.RESET}  并行脉路 {Badge.inline('ACTIVE','ok')}\n"
          f"  {C.CRUX_R}朱雀{C.RESET}  洞察之眼 {Badge.inline('ACTIVE','ok')}      {C.CRUX_C}玄武{C.RESET}  守护甲盾 {Badge.inline('ACTIVE','ok')}\n"
          f"  {C.CRUX_P}麒麟{C.RESET}  创造之手 {Badge.inline('ACTIVE','ok')}      {C.CRUX_Y}螣蛇{C.RESET}  传承记忆 {Badge.inline('ACTIVE','ok')}\n"
          f"  {C.CRUX_O}应龙{C.RESET}  号令八方 {Badge.inline('ACTIVE','ok')}",
          C.CRUX_P, 52)
    time.sleep(1.0)

# ─── 场景5: 状态栏 + 工具链 ─────────────────────────
def scene_toolbar():
    divider("═", C.CRUX_G, "工具栏 · 状态栏")
    time.sleep(0.3)

    status_bar([
        ("CRUX",   "v5.0",  "crux"),
        ("MODEL",  "DeepSeek V4 Flash", "star"),
        ("TASKS",  "7 ACTIVE", "fire"),
        ("MEMORY", "42%", "info"),
    ])
    print()
    status_bar([
        ("白虎", "骨", "ok"),
        ("青龙", "脉", "ok"),
        ("朱雀", "眼", "ok"),
        ("玄武", "甲", "ok"),
        ("麒麟", "手", "ok"),
        ("螣蛇", "忆", "ok"),
        ("应龙", "令", "ok"),
    ])
    print()
    toolchain_display()
    time.sleep(1.0)

# ─── 场景6: 极简英雄 Banner ─────────────────────────
def scene_hero():
    divider("═", C.CRUX_R, "英雄模式 · 大字报")
    time.sleep(0.3)

    # 彩虹大字
    word = "SEVEN"
    colors = [C.CRUX_R, C.CRUX_O, C.CRUX_Y, C.CRUX_G, C.CRUX_B]
    for i, ch in enumerate(word):
        echo(ch, font="banner3-D", color=colors[i % len(colors)])
        time.sleep(0.15)

    print(f"\n\n  {C.BOLD}{C.CRUX_P}平时如刀 · 出事成阵{C.RESET}\n")
    time.sleep(1.0)

# ─── 主入口 ──────────────────────────────────────────
def main():
    try:
        scenes = [
            ("启动 · 七兽觉醒",  scene_boot),
            ("徽章 · 全展示",    scene_badges),
            ("字体 · 巡礼",      scene_fonts),
            ("面板 · 状态监控",  scene_panels),
            ("工具 · 状态栏",    scene_toolbar),
            ("英雄 · 大字报",    scene_hero),
        ]

        for i, (name, fn) in enumerate(scenes, 1):
            print(f"\n{C.DIM}{C.GRAY}═══ 场景 {i}/{len(scenes)}: {name} ═══{C.RESET}")
            time.sleep(0.5)
            fn()

        # ── 收尾 ──
        divider("✦", C.CRUX_P, "演示结束")
        print(f"\n  {C.BOLD}{C.CRUX_R}✦{C.RESET} "
              f"{C.BOLD}{C.WHITE}七兽之力已注入终端{C.RESET} "
              f"{C.BOLD}{C.CRUX_P}✦{C.RESET}")
        print(f"\n  {C.DIM}在 Python 中导入:{C.RESET}")
        print(f"  {C.CRUX_G}from tui_art import *{C.RESET}")
        print(f"  {C.CRUX_G}welcome_screen(){C.RESET}")
        print(f"  {C.CRUX_G}Badge.make('HELLO', 'fire'){C.RESET}")
        print(f"  {C.CRUX_G}echo('CRUX', 'big', C.CRUX_R){C.RESET}")
        print(f"  {C.CRUX_G}panel('标题', '内容', C.CRUX_B){C.RESET}\n")

    except KeyboardInterrupt:
        print(f"\n\n  {C.CRUX_Y}⏎ 演示已退出{C.RESET}\n")
    except Exception as e:
        print(f"\n\n  {C.RED}⚠ 错误: {e}{C.RESET}\n")


if __name__ == "__main__":
    main()
