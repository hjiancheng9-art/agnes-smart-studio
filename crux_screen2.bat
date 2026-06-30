@echo off
chcp 65001 >nul 2>&1
title CRUX Studio · 暗夜指挥台 · 第二屏
cd /d "%~dp0"

echo.
echo   ◆ CRUX 暗夜指挥台 — 七兽共鸣
echo   固定输入框 · 终端原生 · 暗夜工坊
echo   ─────────────────────────────────────
echo.

python -m ui.command_center

echo.
echo   暗夜指挥台已退出。第一屏终端继续运行。
pause
