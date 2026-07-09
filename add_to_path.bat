@echo off
chcp 65001 >nul
title CRUX — 添加到 PATH

set "CRUX_DIR=C:\Users\huangjiancheng\agnes-smart-studio"

:: 检查是否已在 PATH 中
echo %PATH% | find /i "%CRUX_DIR%" >nul
if not errorlevel 1 (
    echo [✓] CRUX 已在 PATH 中，无需重复添加
    pause
    exit /b 0
)

:: 添加到用户 PATH（不污染系统 PATH）
for /f "skip=2 tokens=3*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%a%%b"

if "%USER_PATH%"=="" (
    setx PATH "%CRUX_DIR%"
) else (
    echo %USER_PATH% | find /i "%CRUX_DIR%" >nul
    if errorlevel 1 (
        setx PATH "%USER_PATH%;%CRUX_DIR%"
    ) else (
        echo [✓] 已在 PATH 中
        pause
        exit /b 0
    )
)

if errorlevel 1 (
    echo [✗] 添加失败，请以管理员身份运行
) else (
    echo [✓] 添加成功！重启终端后，任意位置输入 crux 即可启动
)
pause
