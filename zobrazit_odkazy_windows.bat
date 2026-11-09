@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Chybi Python 3 a py launcher.
 pause
 exit /b 1
)
py -3 aprs_service.py --links
echo.
echo Zobrazene prihlasovaci udaje nikomu nesdelej.
pause
