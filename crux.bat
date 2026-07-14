@echo off
title CRUX Studio

:: Save user's original working directory before cd
set "CRUX_WORKSPACE=%CD%"
cd /d "%~dp0"

:: Clear stale bytecode
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PY%" for %%e in (python3 python py) do (where %%e >nul 2>&1 && set "PY=%%e" && goto :run)
if not exist "%PY%" echo Python not found & pause & exit /b 1
:run
:: Default to chat mode only when no subcommand is given;
:: otherwise pass args through so 'crux serve' / 'crux gen' work.
if "%~1"=="" (
    %PY% crux_studio.py -c
) else (
    %PY% crux_studio.py %*
)
if errorlevel 1 (
    echo.
    echo === CRASH DETECTED ===
    if exist "output\crash.log" (
        echo Crash log:
        type "output\crash.log"
    )
    pause
)
