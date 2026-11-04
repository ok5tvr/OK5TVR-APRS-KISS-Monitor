@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo CHYBA: Python 3 nenalezen.
        echo Stahnete Python: https://www.python.org/downloads/windows/
        echo Pri instalaci vyberte Add Python to PATH.
        pause
        exit /b 1
    )
    set "PY=python"
)
%PY% -c "import serial" >nul 2>nul
if errorlevel 1 (
    echo Instaluji pyserial ...
    %PY% -m pip install "pyserial>=3.5"
    if errorlevel 1 %PY% -m pip install --user "pyserial>=3.5"
    if errorlevel 1 (
        echo CHYBA: Instalace pyserial selhala. Zkontrolujte internet a pip.
        pause
        exit /b 1
    )
)
%PY% "aprs_kiss_monitor.py"
if errorlevel 1 pause
