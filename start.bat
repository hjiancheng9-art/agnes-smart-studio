@echo off
:: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
::  Agnes Smart Studio - 一键启动器
::  双击此文件即可启动，自动检测环境并安装依赖
:: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

chcp 65001 >nul 2>&1
title Agnes Smart Studio
cd /d "%~dp0"

:: ── 1. 查找 Python ──────────────────────────
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo.
echo   [错误] 未找到 Python
echo   请安装 Python 3.10+: https://www.python.org/downloads/
echo   安装时勾选 "Add Python to PATH"
echo.
pause
exit /b 1

:found_py

:: ── 2. 检查 .env ────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
    ) else (
        (
            echo # Agnes AI API 配置
            echo AGNES_API_KEY=sk-your-api-key-here
            echo AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
        ) > .env
    )
)

:: ── 3. 检查 API Key ────────────────────────
%PY% -c "from core.config import SETTINGS; import sys; sys.exit(0 if SETTINGS.api_key and 'sk-your' not in SETTINGS.api_key else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo    API Key 未配置
    echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo.
    set /p "KEY=   请输入 AGNES_API_KEY: "
    if not "!KEY!"=="" (
        %PY% -c "from pathlib import Path; p=Path('.env'); lines=[f'AGNES_API_KEY={!KEY!}\n' if l.startswith('AGNES_API_KEY=') else l for l in p.read_text(encoding='utf-8').splitlines(True)]; p.write_text(''.join(lines), encoding='utf-8')"
    )
)

:: ── 4. 安装依赖（静默） ────────────────────
%PY% -c "import httpx, rich, PIL, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   正在安装依赖，请稍候...
    %PY% -m pip install -q -r requirements.txt >nul 2>&1
)

:: ── 5. 创建输出目录 ─────────────────────────
if not exist "output\images" mkdir output\images
if not exist "output\videos" mkdir output\videos

:: ── 6. 启动 ─────────────────────────────────
if "%~1"=="" (
    %PY% agnes_studio.py
) else (
    %PY% agnes_studio.py %*
)
