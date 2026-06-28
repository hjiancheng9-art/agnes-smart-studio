@echo off
chcp 65001 >nul 2>&1
title CRUX Studio v5.0
cd /d "%~dp0"

:: ── VT100 色彩 ──
for /f %%e in ('echo prompt $E ^| cmd') do set "E=%%e"
set "C=%E%[36m"
set "D=%E%[90m"
set "W=%E%[97m"
set "R=%E%[0m"

:: ── 欢迎横幅 ──
cls
echo.
echo  %D%╔══════════════════════════════════════════════════════════════╗%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%║%R%     %C%██████╗%R%  %C%██╗   ██╗%R%  %C%██╗  ██╗%R%                   %D%║%R%
echo  %D%║%R%    %C%██╔════╝%R%  %C%██║   ██║%R%  %C%╚██╗██╔╝%R%                   %D%║%R%
echo  %D%║%R%    %C%██║%R%       %C%██║   ██║%R%  %C% ╚███╔╝%R%                    %D%║%R%
echo  %D%║%R%    %C%██║%R%       %C%██║   ██║%R%  %C% ██╔██╗%R%                    %D%║%R%
echo  %D%║%R%     %C%██████╗%R%  %C%╚██████╔╝%R%  %C%██╔╝ ██╗%R%                   %D%║%R%
echo  %D%║%R%      %C%╚═════╝%R%   %C%╚═════╝%R%   %C%╚═╝  ╚═╝%R%                   %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%║%R%         %W%七兽融合  ·  AI-Native Creative Studio%R%              %D%║%R%
echo  %D%║%R%         %D%v5.0  ·  deepseek-v4-pro  ·  1M context%R%                %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%╚══════════════════════════════════════════════════════════════╝%R%
echo.

:: ── 1. 找 Python ──
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo   %E%[91m[✖]%R% Python 未找到，请安装 Python 3.10+
pause
exit /b 1
:found_py

:: ── 2. 检查依赖 ──
%PY% -c "import httpx, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo   %E%[93m[⬡]%R% 安装依赖中...
    %PY% -m pip install httpx rich python-dotenv nest-asyncio Pillow pyyaml prompt_toolkit playwright edge-tts -q
    if errorlevel 1 (
        echo   %E%[91m[✖]%R% 依赖安装失败
        pause
        exit /b 1
    )
)

:: ── 3. 启动 ──
echo   %E%[92m[✔]%R% 启动 CRUX Studio...
echo.
%PY% crux_studio.py
if errorlevel 1 pause
exit /b 0
