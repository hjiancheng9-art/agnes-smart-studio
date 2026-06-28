@echo off
for /r "C:\Users\huangjiancheng\agnes-smart-studio" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul
echo OK
