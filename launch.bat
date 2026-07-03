@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title CRUX STUDIO — 暗夜工坊

cd /d "%~dp0"
set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PY%" for %%e in (python3 python py) do (where %%e >nul 2>&1 && set "PY=%%e" && goto :run)
if not exist "%PY%" echo Python not found & pause & exit /b 1
:run

:: 先跑健康检查
echo.
echo   -- Health Check --
"%PY%" crux_studio.py --check
if errorlevel 1 (
    echo.
    echo   ! 健康检查未通过，按任意键继续启动或关闭窗口退出。
    pause >nul
)

:: 进入聊天模式
"%PY%" crux_studio.py -c %*
if errorlevel 1 (
    echo.
    echo   ! 程序异常退出，详情见 output\last_error.txt
    pause
)
