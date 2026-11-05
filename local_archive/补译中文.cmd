@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"%~dp0python\python.exe" "%~dp0tools\tweet_archive.py" --root "%~dp0." --translate-only %*
if errorlevel 1 (echo 部分翻译未完成，已成功保存的内容保留，请查看上方提示。)
echo 浏览归档：本目录中的 推文归档.html
pause
