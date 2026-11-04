@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Neni nalezen py.exe a Python 3.
  pause
  exit /b 1
)
py -3 -m pip install pyinstaller "pyserial>=3.5"
if errorlevel 1 exit /b 1
py -3 -m PyInstaller --clean --noconfirm --onefile --windowed ^
 --name OK5TVR_APRS_KISS_Monitor_v1_8 ^
 --add-data "offline_geography.json;." ^
 --add-data "web_dashboard.html;." ^
 --add-data "web_control.html;." ^
 --add-data "web_messages.html;." ^
 --add-data "web_operations.html;." ^
 --add-data "web_locale.js;." aprs_kiss_monitor.py
if errorlevel 1 (
 echo Sestaveni EXE selhalo.
) else (
 echo Hotovo: dist\OK5TVR_APRS_KISS_Monitor_v1_8.exe
)
pause
