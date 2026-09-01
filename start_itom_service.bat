@echo off
setlocal EnableDelayedExpansion
title ITOM Production Server Supervisor (Port 8080)

:: Determine workspace root dynamically
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Locate Python executable
set "PYTHON_EXE="
where python.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python.exe"
) else (
    where py.exe >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py.exe"
    ) else (
        if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
            set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
            set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        ) else if exist "%ProgramFiles%\Python312\python.exe" (
            set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found in PATH or standard installation directories.
    echo Please install Python 3.10+ or add python.exe to system PATH.
    exit /b 1
)

:: Locate Pythonw for silent background execution
set "PYTHONW_EXE=pythonw.exe"
where pythonw.exe >nul 2>nul
if %ERRORLEVEL% neq 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
        set "PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" (
        set "PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    ) else (
        set "PYTHONW_EXE=%PYTHON_EXE%"
    )
)

:: Handle CLI arguments: --status, --stop, --background, --restart
if /i "%~1"=="--status" goto check_status
if /i "%~1"=="-s" goto check_status
if /i "%~1"=="--stop" goto stop_service
if /i "%~1"=="-k" goto stop_service
if /i "%~1"=="--restart" goto restart_service
if /i "%~1"=="-r" goto restart_service
if /i "%~1"=="--background" goto start_background
if /i "%~1"=="-b" goto start_background

:: Default: Foreground Supervisor Execution
echo ================================================================
echo   ITOM Enterprise Portal - Production Web Server Supervisor
echo ================================================================
echo  * Working Directory: %SCRIPT_DIR%
echo  * Python Binary:     %PYTHON_EXE%
echo  * Listening Port:    8080
echo  * Local URL:         http://localhost:8080/
echo  * OPS Analytics:     http://localhost:8080/ops_analytics.html
echo.
echo  Auto-Sync telemetry runs every 10 minutes in the background.
echo  To run silently in background: start_itom_service.bat --background
echo  Press Ctrl+C to stop the foreground supervisor.
echo ================================================================
echo.

"%PYTHON_EXE%" "scripts\start_server.py"
goto :eof

:start_background
echo [*] Starting ITOM Server in detached background daemon mode...
start /b "" "%PYTHONW_EXE%" "%SCRIPT_DIR%scripts\start_server.py" >nul 2>&1
timeout /t 2 /nobreak >nul
goto check_status

:stop_service
echo [*] Terminating active ITOM Server processes on port 8080...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080" ^| findstr "LISTENING"') do (
    echo [*] Killing process PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
echo [✓] Port 8080 is now cleared.
goto :eof

:restart_service
call :stop_service
timeout /t 1 /nobreak >nul
goto start_background

:check_status
echo ================================================================
echo   ITOM Production Server Status Check
echo ================================================================
netstat -aon | findstr ":8080" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% neq 0 goto server_offline

echo [✓] ITOM Server is ONLINE and LISTENING on Port 8080
echo.
"%PYTHON_EXE%" -c "from scripts.start_server import print_status; print_status()"
echo ================================================================
goto :eof

:server_offline
echo [!] ITOM Server is OFFLINE (Port 8080 not listening).
echo Run 'start_itom_service.bat' or 'start_itom_service.bat --background' to start.
echo ================================================================
goto :eof
