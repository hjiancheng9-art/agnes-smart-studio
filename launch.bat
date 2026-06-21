@echo off
chcp 65001 >nul 2>&1
title Agnes Smart Studio v5.0
cd /d "%~dp0"

:: Find Python
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found
)
echo Python not found. Install from https://www.python.org/downloads/
pause
exit /b 1
:found

:: Quick check
%PY% -c "from core.config import SETTINGS; print('Ready')" 2>nul

%PY% agnes_studio.py -c
pause
