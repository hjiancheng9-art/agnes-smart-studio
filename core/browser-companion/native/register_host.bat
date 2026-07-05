@echo off
chcp 65001 >nul
set "MANIFEST=C:\Users\huangjiancheng\agnes-smart-studio\core\browser-companion\native\com.crux.bridge.json"

echo Registering CRUX Native Bridge for Edge...
reg add "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.crux.bridge" /ve /t REG_SZ /d "%MANIFEST%" /f 2>nul

echo Registering CRUX Native Bridge for Chrome...
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.crux.bridge" /ve /t REG_SZ /d "%MANIFEST%" /f 2>nul

echo Done. Restart your browser if needed.
pause
