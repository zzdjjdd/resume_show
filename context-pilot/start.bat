@echo off
chcp 65001 >nul
title Context Pilot
cd /d "%~dp0"

echo ========================================
echo   Context Pilot - Starting...
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found, please install Python 3.8+
    pause
    exit /b 1
)
echo [OK] Python OK

REM Check port 8000
set PORT=8000
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [!] Port 8000 in use, switching to 8001
    set PORT=8001
)

REM Check dependencies
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [..] Installing dependencies...
    pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [X] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready

echo.
echo ========================================
echo   Server:
echo     http://localhost:%PORT%
echo     http://127.0.0.1:%PORT%
echo   Close this window to stop.
echo ========================================
echo.

REM Bypass proxy for localhost
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

REM Start server
python -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% --no-access-log

echo.
echo Server stopped.
pause