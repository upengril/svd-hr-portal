@echo off
title SV DREEAMPLANNERS - Uninstall Cloudflare Tunnel
color 0C

echo ======================================================================
echo           SV DREEAMPLANNERS PRIVATE LIMITED
echo            Uninstall Old Cloudflare Tunnel
echo ======================================================================
echo.

:: Check for Administrator Elevation
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] ERROR: Please right-click this file and select 'Run as administrator'.
    echo.
    pause
    exit /b 1
)

echo [*] Stopping Cloudflare service...
net stop Cloudflared >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1

echo [*] Uninstalling Cloudflare Windows Service...
if exist "%~dp0cloudflared.exe" (
    "%~dp0cloudflared.exe" service uninstall >nul 2>&1
)
sc delete Cloudflared >nul 2>&1

echo [*] Cleaning old token and configuration data...
if exist "C:\ProgramData\cloudflared" (
    rd /s /q "C:\ProgramData\cloudflared" >nul 2>&1
)

echo.
echo ======================================================================
echo [SUCCESS] Cloudflare Tunnel has been completely uninstalled!
echo.
echo Now you can:
echo 1. Delete the old tunnel from Cloudflare Dashboard (Networks -^> Tunnels).
echo 2. Create a brand new tunnel in Cloudflare Zero Trust.
echo 3. Reinstall using the new token!
echo ======================================================================
echo.
pause
