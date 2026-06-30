@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title CRUX STUDIO (Nine Beasts Mesh)
set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
set "SCRIPT=C:\Users\huangjiancheng\agnes-smart-studio\launcher.py"
set "CRUX=C:\Users\huangjiancheng\agnes-smart-studio\crux_studio.py"

if not exist "%PY%" (
    echo ERROR: Python not found at %PY%
    echo Please edit start_launcher.bat and fix the PY path.
    pause
    exit /b 1
)

cd /d "C:\Users\huangjiancheng\agnes-smart-studio"

:: No args = double-click launch: start services + CRUX main window
if "%~1"=="" (
    echo [1/2] Starting background services...
    "%PY%" "%SCRIPT%" --start
    echo [2/2] Launching CRUX Studio main window...
    start "CRUX Studio" "%PY%" "%CRUX%" -c
) else (
    "%PY%" "%SCRIPT%" %*
)
if errorlevel 1 pause
