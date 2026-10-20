@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Python environment missing. Read README.md for setup.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -B -m test_platform.server %*
if errorlevel 1 pause
