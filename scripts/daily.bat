@echo off
REM Dev wrapper: run the daily driver in this console so you can watch it.
REM Task Scheduler does NOT use this file - it runs pythonw.exe scripts\daily.py
REM directly, which is what keeps the 17:00 run windowless.
set PYTHONIOENCODING=utf-8
python "%~dp0daily.py" %*
exit /b %errorlevel%
