@echo off
chcp 65001 >nul 2>&1
title 创建查询快捷方式

cd /d "%~dp0"

::: 获取桌面路径
set "DESKTOP=%USERPROFILE%\Desktop"

::: 创建 VBS 临时脚本来生成快捷方式（BAT无法直接创建.lnk）
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo Set oShellLink = WshShell.CreateShortcut^("%DESKTOP%\CRUX 任务查询.lnk"^)
echo oShellLink.TargetPath = WshShell.CurrentDirectory ^& "\query.bat"
echo oShellLink.WorkingDirectory = WshShell.CurrentDirectory
echo oShellLink.Description = "CRUX Studio - 任务查询（自动查询未完成视频任务）"
echo oShellLink.IconLocation = WshShell.CurrentDirectory ^& "\crux.ico"
echo oShellLink.Save
echo WScript.Echo "OK"
) > _mklink_query.vbs

for /f %%a in ('cscript //nologo _mklink_query.vbs') do set "RESULT=%%a"
del _mklink_query.vbs >nul 2>&1

if "%RESULT%"=="OK" (
    echo.
    echo   [完成] 桌面快捷方式已创建!
    echo   双击桌面上的 "CRUX 任务查询" 即可查询
    echo.
) else (
    echo.
    echo   [提示] 自动创建失败，请手动操作:
    echo   1. 右键桌面 - 新建 - 快捷方式
    echo   2. 位置填: %cd%\query.bat
    echo   3. 名称填: CRUX 任务查询
    echo.
)

pause
