@echo off
chcp 65001 >nul 2>&1
title Agnes Smart Studio v5.0 - Codex Parity
cd /d "%~dp0"

:: --- 1. Find Python ---
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo.
echo   [✖] Python not found
echo       Install Python 3.10+: https://www.python.org/downloads/
echo       Enable "Add Python to PATH" during install
pause
exit /b 1
:found_py
echo.
echo   [◆] Python detected: %PY%

:: --- 2. Check .env ---
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
    ) else (
        (
            echo # Agnes AI API key
            echo AGNES_API_KEY=sk-your-api-key-here
            echo AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
        ) > .env
    )
)

:: --- 3. Check API Key ---
setlocal enableDelayedExpansion
%PY% -c "from core.config import SETTINGS; import sys; sys.exit(0 if SETTINGS.api_key and 'sk-your' not in SETTINGS.api_key and len(SETTINGS.api_key) > 10 else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [◈] API Key not configured
    echo       Edit .env and set AGNES_API_KEY
    echo.
    set /p "KEY=   [◈] Enter AGNES_API_KEY: "
    if not "!KEY!"=="" (
        %PY% -c "import os; p='.env'; lines=open(p,encoding='utf-8').read().splitlines() if os.path.exists(p) else []; lines=[('AGNES_API_KEY=' + os.environ['KEY']) if l.startswith('AGNES_API_KEY=') else l for l in lines]; lines.append('AGNES_API_KEY=' + os.environ['KEY']) if not any(x.startswith('AGNES_API_KEY=') for x in lines) else None; open(p,'w',encoding='utf-8').write(chr(10).join(lines) + chr(10))"
    )
)
endlocal

:: --- 4. Install deps if needed ---
%PY% -c "import httpx, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   [⬡] Installing dependencies...
    %PY% -m pip install httpx rich python-dotenv nest-asyncio -q
)

:: --- 5. Launch ---
echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║                                              ║
echo   ║   ◈ AGNES Smart Studio v5.0                  ║
echo   ║     Codex Parity · AI-Native Creative       ║
echo   ║                                              ║
echo   ╚══════════════════════════════════════════════╝
echo.

%PY% launcher.py
if errorlevel 1 pause
exit /b 0
