@echo off
REM Re-exec self under a 65001 console. Keep every line above ":utf8" ASCII-only.
chcp 65001 >nul
if "%~1"=="_utf8" goto :utf8
cmd /d /c ""%~f0" _utf8 %*"
exit /b %errorlevel%
:utf8

chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%ROOT%\logs\cron.log"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

echo [%date% %time%] ===== FrenchDaily 开始 ===== >> "%LOG%"

REM ---------- 当日去重（同一任务多次触发时跳过） ----------
set "TODAY="
for /f "usebackq delims=" %%d in (`python -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%%Y-%%m-%%d'))"`) do set "TODAY=%%d"
if not defined TODAY (
    echo [%date% %time%] 获取日期失败，终止 >> "%LOG%"
    exit /b 1
)

setlocal enabledelayedexpansion
if exist "%ROOT%\logs\.last_success" (
    set /p LAST_SUCCESS=<"%ROOT%\logs\.last_success"
    if /i "!LAST_SUCCESS!"=="%TODAY%" (
        echo [%date% %time%] 今日（%TODAY%）已成功产出，跳过 >> "%LOG%"
        exit /b 0
    )
)

REM ---------- 预检 ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] 找不到 python，终止 >> "%LOG%"
    exit /b 1
)

REM ---------- 构建（仅今日，不回溯） ----------
python scripts\build.py
if errorlevel 1 (
    echo [%date% %time%] build.py 失败 >> "%LOG%"
    exit /b 1
)

REM ---------- 提交 ----------
where git >nul 2>&1
if not errorlevel 1 (
    git add data site 2>>"%LOG%"
    if not errorlevel 1 (
        git diff --cached --quiet
        if errorlevel 1 (
            git commit -m "frenchdaily: %date%" >>"%LOG%" 2>&1
            if not errorlevel 1 (
                git push origin main >>"%LOG%" 2>&1
                if errorlevel 1 (
                    echo [%date% %time%] git push 失败（本地已保留，下次续推）>> "%LOG%"
                )
            )
        )
    )
)

REM ---------- 成功标记 ----------
> "%ROOT%\logs\.last_success" echo %TODAY%
echo [%date% %time%] ===== FrenchDaily 完成 ===== >> "%LOG%"
exit /b 0
