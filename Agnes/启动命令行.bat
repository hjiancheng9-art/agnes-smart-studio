@echo off
title Agnes AI 命令行 — 交互模式
cd /d "%~dp0"
chcp 936>nul
python -m agnes.cli interactive
pause
