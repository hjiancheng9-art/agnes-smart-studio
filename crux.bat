@echo off
title CRUX Studio (REPL)
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

set "PY=C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" crux_studio.py -c
pause
