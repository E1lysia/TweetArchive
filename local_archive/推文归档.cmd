@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"%~dp0python\python.exe" "%~dp0tools\tweet_archive.py" --root "%~dp0." %*
if errorlevel 1 (echo 部分抓取或翻译未完成，请查看上方提示。) else (echo 推文归档已保存。)
echo 浏览归档：本目录中的 推文归档.html
pause
