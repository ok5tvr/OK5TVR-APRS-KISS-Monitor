@echo off
setlocal
cd /d "%~dp0"
echo POUZE SAMOSTATNA BEZOBSLUZNA SLUZBA - zadne graficke okno.
echo Tuto variantu NIKDY nespoustejte soucasne s desktopovym monitorem.
where py >nul 2>nul
if errorlevel 1 exit /b 1
py -3 -m pip install "pyserial>=3.5"
py -3 aprs_service.py
pause
