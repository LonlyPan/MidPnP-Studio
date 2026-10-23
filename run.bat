@echo off
setlocal
cd /d "%~dp0"
python -m midpnp %*
exit /b %ERRORLEVEL%
