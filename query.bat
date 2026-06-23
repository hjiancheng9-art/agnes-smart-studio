@echo off
:::: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
::::  CRUX Studio - video query
::::  双击此文件，自动查询最近未完成的视频任务
::::  或传入 video_id 参数查询指定任务
::::  ⚠ 必须使用 video_id，不要用 task_id
:::: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

chcp 65001 >nul 2>&1
title CRUX 任务查询
cd /d "%~dp0"

:::: ── 查找 Python ──────────────────────────────
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo.
echo   [错误] 未找到 Python
echo.
pause
exit /b 1

:found_py

:::: ── 安装依赖（静默） ────────────────────────
%PY% -c "import httpx, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   正在安装依赖...
    %PY% -m pip install -q -r requirements.txt >nul 2>&1
)

:::: ── 执行查询 ─────────────────────────────────
:::: 无参数: 自动查找未完成任务 + --watch 轮询等待
if "%~1"=="" (
    %PY% query.py --watch 10
) else (
    %PY% query.py %*
)
pause
