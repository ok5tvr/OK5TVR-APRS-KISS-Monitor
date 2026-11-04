@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Neni nalezen py.exe. Nainstalujte Python 3 z python.org.
    pause
    exit /b 1
)
py -3 -m pip install pyinstaller "pyserial>=3.5"
if errorlevel 1 (
    echo CHYBA: Nepodarilo se nainstalovat PyInstaller.
    pause
    exit /b 1
)
py -3 -m PyInstaller --clean --noconfirm --onefile --windowed --name OK5TVR_APRS_KISS_Monitor_v1_5 --add-data "web_dashboard.html;." --add-data "web_control.html;." --add-data "web_locale.js;." --add-data "offline_geography.json;." aprs_kiss_monitor.py
if errorlevel 1 (
    echo Sestaveni EXE selhalo.
) else (
    echo Hotovo: dist\OK5TVR_APRS_KISS_Monitor_v1_5.exe
)
pause
