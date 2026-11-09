@echo off
setlocal
cd /d "%~dp0"
echo OK5TVR APRS KISS - web pro Windows
echo Webova aplikace: http://127.0.0.1:8765/
echo Nepoustej soucasne s desktopovym monitorem na stejnem COM portu.
call "%~dp0spustit_headless_server_windows.bat"
