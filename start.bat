@echo off
chcp 65001 >nul 2>&1
title CRUX Studio v5.0 — 五兽归位 · AI-Native Studio
cd /d "%~dp0"

:: ── VT100 色彩 ──
for /f %%e in ('echo prompt $E ^| cmd') do set "E=%%e"
set "C=%E%[36m"    & REM 青龙色
set "Y=%E%[33m"    & REM 白虎色
set "G=%E%[32m"    & REM 麒麟色
set "M=%E%[35m"    & REM 朱雀色
set "B=%E%[34m"    & REM 玄武色
set "D=%E%[90m"    & REM 暗色
set "W=%E%[97m"    & REM 亮白
set "R=%E%[0m"     & REM 重置

:: ── 欢迎横幅 ──
cls
echo.
echo  %D%╔══════════════════════════════════════════════════════════════╗%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%║%R%     %C%██████╗%R%  %Y%██████╗%R%  %M%██╗   ██╗%R%  %C%██╗  ██╗%R%                   %D%║%R%
echo  %D%║%R%    %C%██╔════╝%R%  %Y%██╔══██╗%R% %M%██║   ██║%R%  %C%╚██╗██╔╝%R%                   %D%║%R%
echo  %D%║%R%    %C%██║%R%       %Y%██████╔╝%R% %M%██║   ██║%R%  %C% ╚███╔╝%R%                    %D%║%R%
echo  %D%║%R%    %C%██║%R%       %Y%██╔══██╗%R% %M%██║   ██║%R%  %C% ██╔██╗%R%                    %D%║%R%
echo  %D%║%R%     %C%██████╗%R%  %Y%██║  ██║%R% %M%╚██████╔╝%R%  %C%██╔╝ ██╗%R%                   %D%║%R%
echo  %D%║%R%      %C%╚═════╝%R%  %Y%╚═╝  ╚═╝%R%  %M%╚═════╝%R%   %C%╚═╝  ╚═╝%R%                   %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%║%R%         %W%五兽归位  ·  AI-Native Creative Studio%R%              %D%║%R%
echo  %D%║%R%         %D%v5.0  ·  deepseek-v4-pro  ·  1M context%R%                %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%╚══════════════════════════════════════════════════════════════╝%R%
echo.
echo  %D%  ◆%R%  %W%正在初始化内核...%R%

:: ── 1. Find Python ──
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo.
echo   %E%[91m[✖]%R% Python not found
echo       Install Python 3.10+: https://www.python.org/downloads/
echo       Enable "Add Python to PATH" during install
pause
exit /b 1
:found_py
echo   %E%[92m[✔]%R% Python detected: %PY%

:: ── 2. Check .env ──
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
    ) else (
        (
            echo # CRUX AI API key
            echo CRUX_API_KEY=sk-your-api-key-here
            echo CRUX_BASE_URL=https://apihub.agnes-ai.com/v1
        ) > .env
    )
)
echo   %E%[92m[✔]%R% Environment config

:: ── 3. Check API Key ──
setlocal enableDelayedExpansion
%PY% -c "from core.config import SETTINGS; import sys; sys.exit(0 if SETTINGS.api_key and 'sk-your' not in SETTINGS.api_key and len(SETTINGS.api_key) > 10 else 1)" >nul 2>&1
if errorlevel 1 (
    echo   %E%[93m[◈]%R% API Key not configured
    echo.
    set /p "KEY=   %E%[93m[◈]%R% Enter CRUX_API_KEY: "
    if not "!KEY!"=="" (
        %PY% -c "import os; p='.env'; lines=open(p,encoding='utf-8').read().splitlines() if os.path.exists(p) else []; lines=[('CRUX_API_KEY=' + os.environ['KEY']) if l.startswith('CRUX_API_KEY=') or l.startswith('AGNES_API_KEY=') else l for l in lines]; lines.append('CRUX_API_KEY=' + os.environ['KEY']) if not any(x.startswith('CRUX_API_KEY=') or x.startswith('AGNES_API_KEY=') for x in lines) else None; open(p,'w',encoding='utf-8').write(chr(10).join(lines) + chr(10))"
        echo   %E%[92m[✔]%R% API Key saved
    )
) else (
    echo   %E%[92m[✔]%R% API Key configured
)
endlocal

:: ── 4. Install deps if needed ──
%PY% -c "import httpx, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   %E%[93m[⬡]%R% Installing dependencies...
    %PY% -m pip install httpx rich python-dotenv nest-asyncio -q
)
echo   %E%[92m[✔]%R% Dependencies ready

:: ── 5. Register crux command ──
%PY% -m pip install -e . --quiet 2>nul
if errorlevel 1 (
    echo   %E%[90m[◈]%R% crux command skipped (fallback mode)
) else (
    echo   %E%[92m[✔]%R% crux command registered
)

:: ── 6. Launch ──
echo.
echo  %D%  ◆%R%  %W%启动 CRUX Studio...%R%
echo.

crux
if errorlevel 1 (
    echo   %E%[90m[◈]%R% Falling back to launcher...
    %PY% launcher.py
)
if errorlevel 1 pause
exit /b 0
