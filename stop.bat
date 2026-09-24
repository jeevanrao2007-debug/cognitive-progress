@echo off
title CognitiveProgress Stopper
echo =======================================================
echo          Stopping CognitiveProgress Services
echo =======================================================
echo.

echo [INFO] Stopping uvicorn / python backend servers on port 8000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [INFO] Stopping node / vite frontend servers on port 5173...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [SUCCESS] CognitiveProgress services stopped.
echo =======================================================
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
