@echo off
chcp 65001 >nul 2>&1
title Agnes Smart Studio

::: 切换到脚本所在目录
cd /d "%~dp0"

::: 查找 Python（支持 python / python3 / py）
set "PY="
for %%e in (python python3 py) do (
    where %%e >nul 2>&1 && set "PY=%%e" && goto :found_py
)
echo [错误] 未找到 Python，请安装 Python 3.10+
echo 下载地址: https://www.python.org/downloads/
pause
exit /b 1

:found_py

::: 检查 .env
if not exist ".env" (
    echo [提示] 未找到 .env 文件
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [完成] 已从 .env.example 创建 .env
        echo [提示] 请编辑 .env 填入你的 AGNES_API_KEY
        echo.
        notepad .env
    ) else (
        echo [错误] 缺少 .env.example，请手动创建 .env
        pause
        exit /b 1
    )
)

::: 检查并安装依赖
%PY% -c "import httpx, rich, PIL, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动运行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

::: 创建输出目录
if not exist "output\images" mkdir output\images
if not exist "output\videos" mkdir output\videos

::: 启动
echo.
echo ============================================
echo   Agnes Smart Studio 启动中...
echo ============================================
echo.

if "%~1"=="" (
    %PY% launcher.py
) else (
    %PY% agnes_studio.py %*
)

pause
