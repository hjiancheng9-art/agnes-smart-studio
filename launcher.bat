@echo off
title 新烬龙V2 · 启动器
chcp 65001 >nul 2>&1

set "ROOT=C:\Users\huangjiancheng\CodeBuddy\新烬龙V2"
set "WORKSPACE=%ROOT%\artifacts\product-core-baseline\baseline-files"
set "PUBLIC=%WORKSPACE%\public"
set "DATA_DIR=%ROOT%\data\cockpit-projects"
set "PORT=4366"
set "DASH_PORT=4377"

:: Scan system info
call :get_info

:menu
cls
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     🔥 新烬龙V2 · 驾驶舱启动器                       ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Node %NODE_VER%  │  项目: %PROJ_COUNT%  │  版本: v3.0.0   ║
echo ║  驾驶舱: %COCKPIT_STATUS%  │  控制台: %DASH_STATUS%          ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo  ═══════════════════════════════════════════════════
echo.
echo   [1] 🚀 启动驾驶舱        http://localhost:%PORT%
echo   [2] 📊 启动 Dashboard    http://localhost:%DASH_PORT%
echo   [3] 🌐 打开驾驶舱（浏览器）
echo   [4] 🧪 运行质量测试 QA
echo   [5] 🔧 安装依赖
echo   [6] 📂 打开项目目录
echo   [7] ℹ  系统信息
echo   [0] ❌ 退出
echo.
set /p choice="请输入 [0-7]: "

if "%choice%"=="1" goto cockpit
if "%choice%"=="2" goto dashboard
if "%choice%"=="3" goto open
if "%choice%"=="4" goto qa
if "%choice%"=="5" goto install
if "%choice%"=="6" goto data_dir
if "%choice%"=="7" goto info
if "%choice%"=="0" goto end
goto menu

:cockpit
cls
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  🚀 启动驾驶舱                                       ║
echo ║  地址: http://localhost:%PORT%                         ║
echo ║  按 Ctrl+C 停止                                      ║
echo ╚══════════════════════════════════════════════════════╝
echo.
start http://localhost:%PORT%
cd /d "%WORKSPACE%"
node server.js
echo.
pause
goto menu

:dashboard
cls
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  📊 启动 Dashboard                                   ║
echo ║  地址: http://localhost:%DASH_PORT%                    ║
echo ║  按 Ctrl+C 停止                                      ║
echo ╚══════════════════════════════════════════════════════╝
echo.
start http://localhost:%DASH_PORT%
cd /d "%ROOT%"
node dashboard.js
echo.
pause
goto menu

:open
start http://localhost:%PORT%
goto menu

:qa
cls
echo ╔══════════════════════════════════════════════════════╗
echo ║  🧪 运行质量测试                                     ║
echo ╚══════════════════════════════════════════════════════╝
echo.
cd /d "%WORKSPACE%"
npm test
echo.
pause
goto menu

:install
cls
echo ╔══════════════════════════════════════════════════════╗
echo ║  🔧 安装依赖                                        ║
echo ╚══════════════════════════════════════════════════════╝
echo.
cd /d "%WORKSPACE%"
npm install
echo.
pause
goto menu

:data_dir
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
explorer "%DATA_DIR%"
goto menu

:info
cls
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  ℹ 系统信息                                         ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Node.js:    %NODE_VER%                                ║
echo ║  NPM:        %NPM_VER%                                 ║
echo ║  项目版本:   v3.0.0                                    ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  驾驶舱端口: %PORT%                                     ║
echo ║  Dashboard:  %DASH_PORT%                                ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  📁 项目数量: %PROJ_COUNT%                               ║
echo ║  📄 界面文件: %PUBLIC%\index.html                     ║
echo ║  ⚙  服务器:   %WORKSPACE%\server.js                   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo 按任意键返回主菜单...
pause >nul
goto menu

:end
cls
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  新烬龙V2 已退出。烬火不灭。                          ║
echo ╚══════════════════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul
exit /b 0

:get_info
:: Node version
for /f "tokens=*" %%i in ('node --version 2^>nul') do set NODE_VER=%%i
if "%NODE_VER%"=="" set NODE_VER=未安装

:: NPM version
for /f "tokens=*" %%i in ('npm --version 2^>nul') do set NPM_VER=%%i
if "%NPM_VER%"=="" set NPM_VER=未安装

:: Project count
set PROJ_COUNT=0
if exist "%DATA_DIR%" (
    for /f %%i in ('dir /b "%DATA_DIR%\*.json" 2^>nul ^| find /c /v ""') do set PROJ_COUNT=%%i
)

:: Server status check
set COCKPIT_STATUS=🔴 已停止
set DASH_STATUS=🔴 已停止
powershell -Command "
try{ $t=New-Object Net.Sockets.TcpClient; $t.ConnectAsync('127.0.0.1',%PORT%).Wait(300); if($t.Connected){return'1'}; $t.Close() }catch{}
" 2>nul | find "1" >nul && set COCKPIT_STATUS=🟢 运行中

powershell -Command "
try{ $t=New-Object Net.Sockets.TcpClient; $t.ConnectAsync('127.0.0.1',%DASH_PORT%).Wait(300); if($t.Connected){return'1'}; $t.Close() }catch{}
" 2>nul | find "1" >nul && set DASH_STATUS=🟢 运行中

goto :eof
