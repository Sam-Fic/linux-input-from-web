@echo off
setlocal EnableExtensions
rem UTF-8 console so the QR code and Unicode output render correctly.
chcp 65001 >nul
cd /d "%~dp0"

rem Prefer a stable interpreter: python on PATH, then the py launcher.
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo Error: Python 3 was not found on PATH.
    echo Install Python 3 from https://python.org and re-run.
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv "%~dp0venv"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        exit /b 1
    )
)

rem Install deps if missing (covers a pre-existing but incomplete venv).
"%~dp0venv\Scripts\python.exe" -c "import flask, qrcode" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    "%~dp0venv\Scripts\python.exe" -m pip install --quiet flask qrcode
    if errorlevel 1 (
        echo Failed to install dependencies.
        exit /b 1
    )
)

"%~dp0venv\Scripts\python.exe" "%~dp0input-from-web.py" %*
exit /b %errorlevel%
