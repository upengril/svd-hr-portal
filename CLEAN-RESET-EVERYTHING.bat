@echo off
title SV DREEAMPLANNERS - Complete System Reset ^& Cleanup
color 0C

echo ======================================================================
echo           SV DREEAMPLANNERS PRIVATE LIMITED
echo       COMPLETE SYSTEM RESET: Servers, Tunnels ^& Auto-Start
echo ======================================================================
echo.

:: Check Administrator Elevation
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] ERROR: Please right-click this file and select 'Run as administrator'.
    echo.
    pause
    exit /b 1
)

echo [1/4] Stopping Web Server and Background Loop on Port 5000...
powershell -NoProfile -Command ^
    "$conns = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; " ^
    "if ($conns) { " ^
    "    foreach ($c in $conns) { " ^
    "        $pid1 = $c.OwningProcess; " ^
    "        $parent = (Get-CimInstance Win32_Process -Filter \"ProcessId = $pid1\").ParentProcessId; " ^
    "        Write-Host 'Terminating parent loop PID:' $parent 'and server PID:' $pid1; " ^
    "        Stop-Process -Id $parent -Force -ErrorAction SilentlyContinue; " ^
    "        Stop-Process -Id $pid1 -Force -ErrorAction SilentlyContinue; " ^
    "    } " ^
    "} else { Write-Host 'Port 5000 is already free.' }"

:: Also kill any remaining python running main:app
powershell -NoProfile -Command ^
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn backend.main:app*' -or $_.CommandLine -like '*run_server.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo       Done.

echo [2/4] Stopping and Removing Cloudflare Tunnel Service...
net stop Cloudflared >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1
if exist "%~dp0cloudflared.exe" (
    "%~dp0cloudflared.exe" service uninstall >nul 2>&1
)
sc delete Cloudflared >nul 2>&1
if exist "C:\ProgramData\cloudflared" (
    rd /s /q "C:\ProgramData\cloudflared" >nul 2>&1
)
echo       Done.

echo [3/4] Removing Windows Auto-Start Scheduled Task...
schtasks /delete /tn "SVD_HR_Portal_Silent" /f >nul 2>&1
echo       Done.

echo [4/4] Verifying clean state...
powershell -NoProfile -Command ^
    "$chk = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; " ^
    "if ($chk) { Write-Host '       [!] Warning: Port 5000 is still busy.' -ForegroundColor Yellow } " ^
    "else { Write-Host '       [+] Port 5000 is completely FREE and CLOSED.' -ForegroundColor Green }"

sc query Cloudflared >nul 2>&1
if %errorLevel% equ 0 (
    echo       [!] Warning: Cloudflared service still exists.
) else (
    echo       [+] Cloudflared service completely REMOVED.
)

echo.
echo ======================================================================
echo [SUCCESS] Everything has been completely stopped and uninstalled!
echo Your system is now 100%% clean and ready for a fresh setup.
echo ======================================================================
echo.
pause
