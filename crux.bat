@echo off
title CRUX Studio
cd /d "%~dp0"

set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PY%" for %%e in (python3 python py) do (where %%e >nul 2>&1 && set "PY=%%e" && goto :run)
if not exist "%PY%" echo Python not found & pause & exit /b 1
:run
%PY% crux_studio.py -c %*
if errorlevel 1 pause
