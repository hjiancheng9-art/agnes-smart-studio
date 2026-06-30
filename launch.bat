@echo off
chcp 65001 >nul 2>&1
title CRUX Studio
cd /d "%~dp0"

:: Try crux command first (fast path, for installed environments)
where crux >nul 2>&1 && (
    crux %*
    if errorlevel 1 pause
    exit /b 0
)

:: Fallback: find Python and launch directly
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found
)
echo Python not found. Install from https://www.python.org/downloads/
pause
exit /b 1
:found

%PY% crux_studio.py %*
pause
