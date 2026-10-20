@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m framework.quick
set "TEST_EXIT=%ERRORLEVEL%"
pause
exit /b %TEST_EXIT%
