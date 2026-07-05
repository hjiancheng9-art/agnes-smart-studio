@echo off
reg delete "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.crux.bridge" /f 2>nul
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.crux.bridge" /f 2>nul
echo Unregistered.
pause
