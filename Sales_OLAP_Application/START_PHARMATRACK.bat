

@echo off
setlocal
title PharmaTrack DW: Medicine Demand, Pharmacy and Hospital Access Intelligence Warehouse
set "APP_URL=http://localhost:5000/"
echo ===============================================================================
echo  PharmaTrack DW: Medicine Demand, Pharmacy & Hospital Intelligence Warehouse
echo ===============================================================================
echo.

set "TARGET_DIR=%~dp0Sales_OLAP_Application"
if exist "%TARGET_DIR%\app.py" (
    cd /d "%TARGET_DIR%"
) else (
    cd /d "%~dp0"
)

echo Project Directory: %CD%
echo.

REM Find Python. Prefer PATH, then the per-user installations commonly used on Windows.
set "PYTHON_CMD="
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 set "PYTHON_CMD=python"
if defined PYTHON_CMD (
    "%PYTHON_CMD%" --version >nul 2>&1
    if errorlevel 1 set "PYTHON_CMD="
)
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON_CMD (
    echo [ERROR] Python was not found in your PATH.
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)
"%PYTHON_CMD%" --version
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] The selected Python interpreter could not start.
    pause
    exit /b 1
)

REM Ensure .env configuration file exists
if not exist ".env" (
    if exist ".env.example" (
        echo [SETUP] Creating initial configuration .env from .env.example...
        copy ".env.example" ".env" >nul
    )
    
)

REM Check if Data Warehouse exists; if not, initialize and run ETL
if not exist "pharmatrack_dw.sqlite" (
    echo [SETUP] Initializing Data Warehouse...
    "%PYTHON_CMD%" migrate_db.py
    "%PYTHON_CMD%" etl.py
)

REM Reuse a running server if its TCP port is accepting local connections.
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try {$c.Connect('127.0.0.1',5000); exit 0} catch {exit 1} finally {$c.Dispose()}" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto OPEN_BROWSER

echo Starting the PharmaTrack server. A separate server window will show any startup errors.
start "PharmaTrack DW Server" /D "%CD%" "%PYTHON_CMD%" app.py

set /a WAIT_COUNT=0
:WAIT_FOR_SERVER
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try {$c.Connect('127.0.0.1',5000); exit 0} catch {exit 1} finally {$c.Dispose()}" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto OPEN_BROWSER
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 goto SERVER_FAILED
goto WAIT_FOR_SERVER

:OPEN_BROWSER
echo PharmaTrack is ready. Opening %APP_URL% ...
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" goto OPEN_EDGE_X86
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" goto OPEN_EDGE_X64
if exist "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" goto OPEN_EDGE_USER
start "" "%APP_URL%"
goto :eof

:OPEN_EDGE_X86
start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --new-window "%APP_URL%"
goto :eof

:OPEN_EDGE_X64
start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --new-window "%APP_URL%"
goto :eof

:OPEN_EDGE_USER
start "" "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" --new-window "%APP_URL%"
goto :eof

:SERVER_FAILED
echo [ERROR] PharmaTrack did not respond on port 5000 after 30 seconds.
echo Check the separate "PharmaTrack DW Server" window for the Python error.
pause
