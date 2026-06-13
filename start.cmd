@echo off
REM Launcher for the table booking system (Windows).
REM Double-click this file to start the app.
REM
REM NOTE: keep this file ASCII-only. Putting Cyrillic text together with
REM "chcp 65001" inside a .cmd desyncs the cmd parser and breaks the script.
REM Russian text is printed by Python instead (UTF-8 mode is enabled below).

REM Switch console to UTF-8 so the Python wizard's Russian text shows correctly.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"

REM Pick an available Python launcher.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

echo Installing dependencies...
%PY% -m pip install -r requirements.txt

echo Starting application...
%PY% app.py

pause
