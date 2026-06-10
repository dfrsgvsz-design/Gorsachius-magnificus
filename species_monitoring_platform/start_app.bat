@echo off
setlocal
cd /d "%~dp0"

echo Starting Biodiversity Field Survey Platform...
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launcher.py
  goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
  python launcher.py
  goto :end
)

echo Python 3 was not found on this machine.
echo Please install Python 3 and then run this script again.
echo.
pause

:end
endlocal
