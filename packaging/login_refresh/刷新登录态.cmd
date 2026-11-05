@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%~dp0python\python.exe" -X utf8 "%~dp0_setup\grab_cookies.py"
echo.
pause
