@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title CRUX STUDIO v5.0 — 暗夜工坊 · 七兽互联

:: ── Atelier 暗夜配色 ──────────────────────────────────
:: 熔金 = 33 (yellow), 翠绿 = 32 (green), 朱砂 = 31 (red)
:: 青玉 = 36 (cyan), 暗哑 = 90 (bright black), 暖白 = 37 (white)
set "GOLD=[33m"
set "JADE=[32m"
set "CINN=[31m"
set "AZURE=[36m"
set "DIM=[90m"
set "WARM=[37m"
set "BOLD=[1m"
set "RESET=[0m"

:: ── 路径自动探测 ──────────────────────────────────────
set "ROOT=C:\Users\huangjiancheng\agnes-smart-studio"

:: 尝试多个 Python 安装位置
set "PY="
if exist "C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PY if exist "C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python312\python.exe" set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python312\python.exe"
if not defined PY if exist "C:\Python311\python.exe" set "PY=C:\Python311\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe" set "PY=%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe"
if not defined PY for /f "tokens=*" %%i in ('where python 2^>nul') do (set "PY=%%i" & goto :py_found)
:py_found

set "LAUNCHER=%ROOT%\launcher.py"
set "CRUX=%ROOT%\crux_studio.py"

:: ── 依赖检查 ──────────────────────────────────────────
if not defined PY (
    echo %CINN%✗ Python not found. Please install Python 3.11+%RESET%
    echo     Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "%LAUNCHER%" (
    echo %CINN%✗ launcher.py not found at %LAUNCHER%%RESET%
    pause
    exit /b 1
)

:: ── Atelier 工坊 Banner ────────────────────────────────
cls
echo.
echo   %GOLD%╔══════════════════════════════════════════════════╗%RESET%
echo   %GOLD%║%RESET%  %BOLD%%GOLD%⚒  CRUX  STUDIO%RESET%%DIM%  ·  暗夜工坊 · 七兽互联  %GOLD%║%RESET%
echo   %GOLD%║%RESET%  %WARM%白虎为骨%RESET%%DIM% · %RESET%%AZURE%青龙为脉%RESET%%DIM% · %RESET%%CINN%朱雀为眼%RESET%              %GOLD%║%RESET%
echo   %GOLD%║%RESET%  %DIM%玄武为甲 · %WARM%麒麟为手 · %GOLD%螣蛇为忆%RESET%              %GOLD%║%RESET%
echo   %GOLD%║%RESET%  %GOLD%应龙为令%RESET%%DIM% · MCP 网格 · 万象共生%RESET%                %GOLD%║%RESET%
echo   %GOLD%╚══════════════════════════════════════════════════╝%RESET%
echo.

:: ── Python 版本检查 ───────────────────────────────────
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo %GOLD%◆ Python 3.9+ required. Current:%RESET%
    "%PY%" --version
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('"%PY%" --version') do echo   %JADE%● %%v%RESET%
echo   %JADE%● Launcher: launcher.py%RESET%
echo.

:: ── 切换工作目录 ─────────────────────────────────────
cd /d "%ROOT%"

:: ── 命令分发 ──────────────────────────────────────────
if /i "%~1"=="--stop"    goto :cmd_stop
if /i "%~1"=="--status"  goto :cmd_status
if /i "%~1"=="--tools"   goto :cmd_tools
if /i "%~1"=="--help"    goto :cmd_help
if /i "%~1"=="-h"        goto :cmd_help
if /i "%~1"=="/?"        goto :cmd_help

:: 有参数：透传给 launcher.py
if not "%~1"=="" (
    "%PY%" "%LAUNCHER%" %*
    if errorlevel 1 pause
    exit /b %errorlevel%
)

:: ── 无参数：一键启动（默认模式）─────────────────────────
:cmd_launch
echo   %GOLD%[1/3]%RESET% 健康检查 + 服务启动...
"%PY%" "%LAUNCHER%" --launch
if errorlevel 1 (
    echo.
    echo   %CINN%✗ 启动失败，请检查上方错误信息%RESET%
    pause
    exit /b 1
)
echo.
echo   %JADE%● 启动完成。暗夜工坊已就绪。%RESET%
echo.
exit /b 0

:: ── 子命令：停止 ─────────────────────────────────────
:cmd_stop
echo   %GOLD%◆ 正在停止所有后台服务...%RESET%
"%PY%" "%LAUNCHER%" --stop
if errorlevel 1 (
    echo   %CINN%✗ 停止失败%RESET%
    pause
) else (
    echo   %JADE%● 服务已全部停止%RESET%
)
exit /b 0

:: ── 子命令：状态 ─────────────────────────────────────
:cmd_status
"%PY%" "%LAUNCHER%" --status
exit /b 0

:: ── 子命令：工具目录 ─────────────────────────────────
:cmd_tools
"%PY%" "%LAUNCHER%" --tools
exit /b 0

:: ── 帮助 ──────────────────────────────────────────────
:cmd_help
echo.
echo   %BOLD%%GOLD%用法:%RESET%
echo     start_launcher.bat          一键启动（推荐）
echo     start_launcher.bat --start  仅启动后台服务
echo     start_launcher.bat --stop   停止所有服务
echo     start_launcher.bat --status 查看服务状态
echo     start_launcher.bat --tools  查看 TRM 工具目录
echo     start_launcher.bat --help   显示此帮助
echo.
echo   %BOLD%%GOLD%高级用法:%RESET%
echo     其余参数会透传给 launcher.py:
echo     start_launcher.bat --no-check --launch  跳过健康检查直接启动
echo.
exit /b 0
