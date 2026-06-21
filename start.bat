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
echo   [ERROR] Python not found
echo   Install Python 3.10+: https://www.python.org/downloads/
echo   Enable "Add Python to PATH" during install
pause
exit /b 1
:found_py

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
%PY% -c "from core.config import SETTINGS; import sys; sys.exit(0 if SETTINGS.api_key and 'sk-your' not in SETTINGS.api_key and len(SETTINGS.api_key) > 10 else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [WARNING] API Key not configured
    echo   Edit .env and set AGNES_API_KEY
    echo.
    set /p "KEY=   Enter AGNES_API_KEY: "
    if not "!KEY!"=="" (
        %PY% -c "from pathlib import Path; lines=Path('.env').read_text().split('
'); Path('.env').write_text('
'.join([('AGNES_API_KEY='+('!KEY!' if l.startswith('AGNES_API_KEY=') else l.split('=',1)[1] if '=' in l else l) for l in lines]))"
    )
)

:: --- 4. Install deps if needed ---
%PY% -c "import httpx, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   Installing dependencies...
    %PY% -m pip install httpx rich python-dotenv nest-asyncio -q
)

:: --- 5. Launch ---
echo.
echo ============================================
echo   Agnes Smart Studio v5.0 - Codex Parity
echo ============================================
echo.

%PY% launcher.py
if errorlevel 1 pause
exit /b 0
