@echo off
setlocal
cd /d "%~dp0"

if exist "dist\MidPnPStudio\MidPnPStudio.exe" (
    start "" "dist\MidPnPStudio\MidPnPStudio.exe" %*
    exit /b 0
)

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3.10+ and add it to PATH.
        pause
        exit /b 1
    )
    set "PY=python"
)

"%PY%" -m midpnp %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
