@echo off
setlocal
cd /d "%~dp0"
echo OK5TVR APRS v1.4 - headless rezim (web)
where py >nul 2>nul
if errorlevel 1 (
  echo Chybi Python 3 a py launcher.
  pause
  exit /b 1
)
py -3 -m pip show pyserial >nul 2>nul
if errorlevel 1 py -3 -m pip install "pyserial>=3.5"
py -3 aprs_service.py
pause
