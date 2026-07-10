@echo off
cd /d "%~dp0"
echo ========================================
echo   Agnes AI 工具箱
echo   多模态 AI — 对话 · 图片 · 视频
echo ========================================
echo.
echo   [1] 启动图形界面（推荐）
echo   [2] 命令行交互模式
echo   [3] 查询工具（视频状态/模型）
echo   [4] 查看 README
echo   [0] 退出
echo.
echo ========================================
echo.
set /p choice="请输入数字："

if "%choice%"=="1" start "" pythonw.exe "%~dp0launcher.pyw"
if "%choice%"=="2" start cmd /k "cd /d %~dp0 && python -m agnes.cli interactive"
if "%choice%"=="3" start "" pythonw.exe "%~dp0query_tool.pyw"
if "%choice%"=="4" start notepad "%~dp0README.md"
if "%choice%"=="0" exit
