@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"%~dp0python\python.exe" "%~dp0tools\deepl_translate.py" --root "%~dp0." --configure
echo.
pause
