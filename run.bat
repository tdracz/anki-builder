@echo off
REM ---------------------------------------------------------------------------
REM Vocab Builder — one-command launcher (Windows)
REM
REM First run:  creates .venv, installs Python + Node deps, builds frontend
REM Subsequent: skips steps that are already done, starts the server
REM
REM Usage:
REM   run.bat              — start on default port 8000
REM   run.bat --rebuild    — force frontend rebuild before starting
REM   run.bat --port 8080  — use a different port
REM   run.bat --no-browser — don't open the browser automatically
REM ---------------------------------------------------------------------------

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set VENV=%SCRIPT_DIR%.venv
set PYTHON=%VENV%\Scripts\python.exe
set PIP=%VENV%\Scripts\pip.exe

REM ---- 1. Python virtualenv ------------------------------------------------
if not exist "%PYTHON%" (
    echo ^> Creating Python virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python 3.11+ is installed and on your PATH.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created at .venv\
) else (
    echo [OK] Virtual environment already exists
)

REM ---- 2. Python dependencies ----------------------------------------------
set STAMP=%VENV%\.deps_installed
if not exist "%STAMP%" (
    goto install_deps
)
REM Check if requirements.txt is newer than stamp
for %%F in (requirements.txt) do set REQ_TIME=%%~tF
for %%F in ("%STAMP%") do set STAMP_TIME=%%~tF
if "%REQ_TIME%" GTR "%STAMP_TIME%" goto install_deps
echo [OK] Python dependencies up to date
goto node_deps

:install_deps
echo ^> Installing Python dependencies...
"%PIP%" install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies.
    pause
    exit /b 1
)
echo. > "%STAMP%"
echo [OK] Python dependencies installed

REM ---- 3. Node dependencies ------------------------------------------------
:node_deps
if not exist "frontend\node_modules" (
    echo ^> Installing Node dependencies...
    npm install --prefix frontend --silent
    if errorlevel 1 (
        echo ERROR: Failed to install Node dependencies.
        echo Make sure Node.js is installed and on your PATH.
        pause
        exit /b 1
    )
    echo [OK] Node dependencies installed
) else (
    echo [OK] Node dependencies already installed
)

REM ---- 4. Start ------------------------------------------------------------
echo.
echo Starting Vocab Builder...
echo.

"%PYTHON%" start.py %*
