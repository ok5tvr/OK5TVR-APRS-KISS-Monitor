@echo off
setlocal
cd /d "%~dp0"
echo OK5TVR APRS: jednotna webova konzole pro Windows i Raspberry Pi.
echo Po spusteni otevri http://127.0.0.1:8765/
echo Samostatny nativni monitor je stale dostupny pres spustit.bat.
call "%~dp0spustit_headless_server_windows.bat"
