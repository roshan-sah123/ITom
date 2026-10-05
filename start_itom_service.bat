@echo off
setlocal
title ITOM Local Portal and Sync Supervisor
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE="
if "%PYTHON_EXE%"=="" (
where python.exe >nul 2>nul
if %ERRORLEVEL% equ 0 set "PYTHON_EXE=python.exe"
)
if "%PYTHON_EXE%"=="" (
    where py.exe >nul 2>nul
    if %ERRORLEVEL% equ 0 set "PYTHON_EXE=py.exe"
)
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if "%PYTHON_EXE%"=="" if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found. Install Python 3.10+ and add it to PATH.
    exit /b 1
)

"%PYTHON_EXE%" "scripts\local_itom_supervisor.py" %*
exit /b %ERRORLEVEL%
