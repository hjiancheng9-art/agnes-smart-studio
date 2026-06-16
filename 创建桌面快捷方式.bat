@echo off
chcp 65001 >nul 2>&1
title 创建桌面快捷方式

cd /d "%~dp0"

:: 获取桌面路径
set "DESKTOP=%USERPROFILE%\Desktop"

:: 创建 VBS 临时脚本来生成快捷方式（BAT无法直接创建.lnk）
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo Set oShellLink = WshShell.CreateShortcut^("%DESKTOP%\Agnes Smart Studio.lnk"^)
echo oShellLink.TargetPath = WshShell.CurrentDirectory ^& "\launch.bat"
echo oShellLink.WorkingDirectory = WshShell.CurrentDirectory
echo oShellLink.Description = "Agnes Smart Studio - AI图片/视频生成"
echo oShellLink.IconLocation = WshShell.CurrentDirectory ^& "\agnes.ico"
echo oShellLink.Save
echo WScript.Echo "OK"
) > _mklink.vbs

for /f %%a in ('cscript //nologo _mklink.vbs') do set "RESULT=%%a"
del _mklink.vbs >nul 2>&1

if "%RESULT%"=="OK" (
    echo.
    echo   [完成] 桌面快捷方式已创建!
    echo   双击桌面上的 "Agnes Smart Studio" 即可启动
    echo.
) else (
    echo.
    echo   [提示] 自动创建失败，请手动操作:
    echo   1. 右键桌面 - 新建 - 快捷方式
    echo   2. 位置填: %cd%\launch.bat
    echo   3. 名称填: Agnes Smart Studio
    echo.
)

pause
