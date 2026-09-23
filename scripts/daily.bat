@echo off
REM Dev wrapper: run the daily driver in this console so you can watch it.
REM Task Scheduler does NOT use this file - it runs pythonw.exe scripts\daily.py
REM directly, which is what keeps the 17:00 run windowless.
REM
REM PYTHON below must be the interpreter that has edge_tts + requests. The
REM Microsoft Store "python" stub and any stripped-down venv will not do.
set PYTHONIOENCODING=utf-8
set PYTHON=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PYTHON%" set PYTHON=python
"%PYTHON%" "%~dp0daily.py" %*
exit /b %errorlevel%
