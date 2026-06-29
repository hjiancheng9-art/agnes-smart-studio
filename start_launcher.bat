@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title NINE BEASTS LAUNCHER (CRUX + ZCode + 7 beasts)
set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
set "SCRIPT=C:\Users\huangjiancheng\agnes-smart-studio\launcher.py"

if not exist "%PY%" (
    echo ERROR: Python not found at %PY%
    echo Please edit start_launcher.bat and fix the PY path.
    pause
    exit /b 1
)

cd /d "C:\Users\huangjiancheng\agnes-smart-studio"

:: No args = double-click launch: health-check + start services + main window
if "%~1"=="" (
    "%PY%" "%SCRIPT%" --launch
) else (
    "%PY%" "%SCRIPT%" %*
)
if errorlevel 1 pause
