@echo off
title CognitiveProgress Launcher
setlocal enabledelayedexpansion

echo =======================================================
echo     CognitiveProgress - Enterprise Launcher
echo =======================================================
echo.

cd /d "%~dp0"

:: 1. Check Python
set "PYTHON_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=py"
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python is not found in PATH.
    echo Please install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_CMD%

:: 2. Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not found in PATH.
    echo Please install Node.js 18+ and add it to PATH.
    pause
    exit /b 1
)

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not found in PATH.
    pause
    exit /b 1
)

echo [OK] Node.js and npm detected.

:: 3. Setup backend and frontend environment files if missing
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        echo [INFO] Initializing backend\.env from template...
        copy "backend\.env.example" "backend\.env" >nul
    )
)

if not exist "frontend\.env" (
    if exist "frontend\.env.example" (
        echo [INFO] Initializing frontend\.env from template...
        copy "frontend\.env.example" "frontend\.env" >nul
    )
)

:: 4. Check backend virtual environment and dependencies
if not exist "backend\.venv\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment in backend\.venv...
    %PYTHON_CMD% -m venv backend\.venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Installing backend dependencies...
    backend\.venv\Scripts\python.exe -m pip install --upgrade pip
    backend\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
)

:: 5. Check frontend node_modules
if not exist "frontend\node_modules" (
    echo [INFO] Frontend node_modules not found. Installing packages...
    cd frontend
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed.
        cd ..
        pause
        exit /b 1
    )
    cd ..
)

:: 6. Stop any stale processes holding port 8000 or 5173
echo [INFO] Checking ports 8000 and 5173...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [INFO] Freeing port 8000 - PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo [INFO] Freeing port 5173 - PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: 7. Start Backend Server (FastAPI / Uvicorn)
echo [INFO] Starting Backend Server (FastAPI on http://127.0.0.1:8000)...
start "CognitiveProgress - Backend" cmd /k "cd /d ""%~dp0backend"" && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: 8. Wait for backend to be ready
echo [INFO] Waiting for backend to initialize...
timeout /t 3 /nobreak >nul 2>&1 || ping -n 4 127.0.0.1 >nul

:: 9. Start Frontend Dev Server (Vite)
echo [INFO] Starting Frontend Dev Server (Vite on http://127.0.0.1:5173)...
start "CognitiveProgress - Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev -- --host 127.0.0.1 --port 5173"

:: 10. Wait and launch browser
timeout /t 3 /nobreak >nul 2>&1 || ping -n 4 127.0.0.1 >nul
echo [INFO] Launching CognitiveProgress Dashboard in default browser...
start http://127.0.0.1:5173

echo.
echo =======================================================
echo   CognitiveProgress is now running!
echo =======================================================
echo.
echo   - Frontend Dashboard: http://127.0.0.1:5173
echo   - Backend API:        http://127.0.0.1:8000
echo   - Interactive Docs:   http://127.0.0.1:8000/docs
echo   - Health Endpoint:    http://127.0.0.1:8000/api/v1/health
echo.
echo   Quickstart:
echo   1. Navigate to http://127.0.0.1:5173
echo   2. Access the active project or click "Reset Baseline"
echo      to initialize the multi-source dataset and pipeline.
echo   3. Explore the Reconciliation Center, Evidence Feed,
echo      Planner Reviews, and Audit Trail.
echo.
echo   To stop all services:
echo   Run stop.bat or close both command prompt windows.
echo =======================================================
echo.
pause
