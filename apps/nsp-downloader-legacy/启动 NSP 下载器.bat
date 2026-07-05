@echo off
chcp 65001 >nul 2>&1
title NSP 下载器
cd /d "%~dp0"

:: ── VT100 色彩 ──
for /f %%e in ('echo prompt $E ^| cmd') do set "E=%%e"
set "C=%E%[36m"
set "G=%E%[32m"
set "D=%E%[90m"
set "W=%E%[97m"
set "R=%E%[0m"
set "Y=%E%[33m"
set "M=%E%[95m"

cls
echo.
echo  %D%╔══════════════════════════════════════════╗%R%
echo  %D%║%R%     %C%███╗%R%  %Y%███╗%R%  %M%██╗   ██║%R%  %C%██╗  ██╗%R%     %D%║%R%
echo  %D%║%R%    %C%██╔════╝%R%  %Y%██╔══██╗%R% %M%██║   ██║%R%  %C%╚██╗██╔╝%R%     %D%║%R%
echo  %D%║%R%    %C%██║%R%       %Y%██████╔╝%R% %M%██║   ██║%R%  %C% ╚███╔╝%R%      %D%║%R%
echo  %D%║%R%    %C%██║%R%       %Y%██╔══██╗%R% %M%██║   ██║%R%  %C% ██╔██╗%R%      %D%║%R%
echo  %D%║%R%     %C%██████╗%R%  %Y%██║  ██║%R% %M%╚██████╔╝%R%  %C%██╔╝ ██╗%R%     %D%║%R%
echo  %D%║%R%      %C%╚═════╝%R%  %Y%╚═╝  ╚═╝%R%  %M%╚═════╝%R%   %C%╚═╝  ╚═╝%R%     %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%║%R%         %W%NSP 下载器%R%              %D%║%R%
echo  %D%║%R%         %D%HLS/MP4 自动提取 · 断点续传%R%                %D%║%R%
echo  %D%║%R%                                                          %D%║%R%
echo  %D%╚══════════════════════════════════════════╝%R%
echo.

:: ── 1. Find Node.js ──
set "NODE="
where node >nul 2>&1 && set "NODE=node" && goto :found_node
echo   %E%[91m[✖]%R% Node.js 未找到
echo       请从 https://nodejs.org/ 安装 Node.js
pause
exit /b 1
:found_node
echo   %E%[92m[✔]%R% Node.js: %NODE%

:: ── 2. Check port ──
netstat -ano 2>nul | findstr "127.0.0.1:17080" >nul 2>&1
if %errorlevel% equ 0 (
    echo   %E%[93m[◈]%R% 下载器已在端口 17080 运行
)

:: ── 3. Compile TypeScript if needed ──
if not exist "dist\main\index.js" (
    echo   %E%[93m[⬡]%R% 首次运行 — 编译项目...
    call npm run build
    if %errorlevel% neq 0 (
        echo   %E%[91m[✖]%R% 编译失败
        pause
        exit /b 1
    )
)

:: ── 4. Launch ──
echo.
echo  %D%  ◆%R%  %W%启动 NSP 下载器...%R%
echo.
call npx electron .
echo.
echo  %D%  ◆%R%  %W%下载器已启动%R%
echo    后台运行中 — 浏览器插件监听 127.0.0.1:17080
echo.

cd /d "%~dp0"
timeout /t 3 >nul
exit /b 0
