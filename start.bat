@echo off
setlocal
title JobPulse - Local Job Automation Dashboard
cd /d "%~dp0"

echo ========================================================
echo    Starting JobPulse: Local Job Dashboard and Copilot
echo ========================================================

set "PYTHON_EXE="

if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    where python >nul 2>&1
    if errorlevel 0 (
        python -c "import fastapi" >nul 2>&1
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)

if not defined PYTHON_EXE (
    where py >nul 2>&1
    if errorlevel 0 (
        py -c "import fastapi" >nul 2>&1
        if not errorlevel 1 set "PYTHON_EXE=py"
    )
)

if not defined PYTHON_EXE (
    echo.
    echo [ERROR] Could not find a Python environment with required packages.
    echo Please ensure Python 3.11+ and dependencies are installed.
    echo.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_EXE%
echo [OK] Launching JobPulse services...
echo.

"%PYTHON_EXE%" "%~dp0start.py"

if errorlevel 1 (
    echo.
    echo JobPulse stopped with error code %ERRORLEVEL%.
    pause
)
