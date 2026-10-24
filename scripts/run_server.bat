@echo off
setlocal
cd /d "%~dp0.."

if not exist "logs" mkdir "logs"

echo ====================================================================== >> "logs\server.log"
echo [START] SVD HR Portal Auto-Runner Initialized at %date% %time% >> "logs\server.log"
echo ====================================================================== >> "logs\server.log"

:loop
echo [%date% %time%] Starting FastAPI Server on port 5000... >> "logs\server.log"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 >> "logs\server.log" 2>&1

echo [%date% %time%] Server process stopped or restart requested. Restarting in 2 seconds... >> "logs\server.log"
timeout /t 2 /nobreak >nul
goto loop
