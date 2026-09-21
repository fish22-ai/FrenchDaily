@echo off
REM FrenchDaily daily build. Launched hidden by run_hidden.vbs from Task Scheduler.
REM
REM Two rules keep this file safe, do not break them:
REM   1. CRLF line endings. cmd.exe mis-parses LF-only batch files, which turns
REM      the goto below into a self re-exec loop (this really happened: a few
REM      hundred cmd.exe processes in a minute).
REM   2. ASCII only. No codepage dependency, so the old self re-exec (the only
REM      recursive construct in this file) is gone for good.
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%ROOT%\logs\cron.log"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

REM --- lock: a lock older than a day is left over from a crashed run ---
if exist "%ROOT%\logs\.running" (
    forfiles /p "%ROOT%\logs" /m ".running" /d -1 /c "cmd /c del @path" >nul 2>&1
)
if exist "%ROOT%\logs\.running" (
    echo [%date% %time%] another run is in progress, skip >> "%LOG%"
    exit /b 0
)
> "%ROOT%\logs\.running" echo %date% %time%
chcp 65001 >nul 2>&1
echo [%date% %time%] ===== FrenchDaily start ===== >> "%LOG%"

REM --- one build per day ---
set "TODAY="
for /f "usebackq delims=" %%d in (`python -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%%Y-%%m-%%d'))"`) do set "TODAY=%%d"
if not defined TODAY (
    echo [%date% %time%] cannot resolve date, abort >> "%LOG%"
    del "%ROOT%\logs\.running" >nul 2>&1
    exit /b 1
)

setlocal enabledelayedexpansion
if exist "%ROOT%\logs\.last_success" (
    set /p LAST_SUCCESS=<"%ROOT%\logs\.last_success"
    if /i "!LAST_SUCCESS!"=="%TODAY%" (
        echo [%date% %time%] already built for %TODAY%, skip >> "%LOG%"
        endlocal
        del "%ROOT%\logs\.running" >nul 2>&1
        exit /b 0
    )
)
endlocal

REM --- precheck ---
where python >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] python not on PATH, abort >> "%LOG%"
    del "%ROOT%\logs\.running" >nul 2>&1
    exit /b 1
)

REM --- build: today only, never backfills missed days ---
python scripts\build.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] build.py failed >> "%LOG%"
    del "%ROOT%\logs\.running" >nul 2>&1
    exit /b 1
)

REM --- publish ---
where git >nul 2>&1
if not errorlevel 1 (
    git add data site >> "%LOG%" 2>&1
    git diff --cached --quiet
    if errorlevel 1 (
        git commit -m "frenchdaily: %date%" >> "%LOG%" 2>&1
        if not errorlevel 1 (
            git push origin main >> "%LOG%" 2>&1
            if errorlevel 1 echo [%date% %time%] git push FAILED, kept locally, retry next run >> "%LOG%"
        )
    )
)

> "%ROOT%\logs\.last_success" echo %TODAY%
del "%ROOT%\logs\.running" >nul 2>&1
echo [%date% %time%] ===== FrenchDaily done ===== >> "%LOG%"
exit /b 0
