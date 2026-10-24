@echo off
title SV DREEAMPLANNERS - Connect Cloudflare Tunnel
color 0A

echo ======================================================================
echo           SV DREEAMPLANNERS PRIVATE LIMITED
echo              Connect Cloudflare Tunnel
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

cd /d "%~dp0"

if not exist "cloudflared.exe" (
    echo [!] ERROR: cloudflared.exe not found in this folder!
    pause
    exit /b 1
)

echo ======================================================================
echo  CLOUDFLARE TOKEN / COMMAND ENTER KAREIN:
echo  (Aap Cloudflare se jo bhi copy karte hain, seedha yahan paste kar dein)
echo ======================================================================
echo.
set /p CF_INPUT="PASTE HERE: "

if not defined CF_INPUT (
    echo [!] Empty input. Cancelled.
    pause
    exit /b 1
)

:: Extract token if full command was pasted
set "TOKEN=%CF_INPUT%"
set "TOKEN=%TOKEN:cloudflared.exe service install =%"
set "TOKEN=%TOKEN:cloudflared service install =%"
set "TOKEN=%TOKEN:cloudflared.exe =%"
set "TOKEN=%TOKEN:cloudflared =%"
set "TOKEN=%TOKEN:"=%"

:: Trim leading spaces
for /f "tokens=* delims= " %%a in ("%TOKEN%") do set "TOKEN=%%a"

echo.
echo [*] Cleaning previous service if any...
net stop Cloudflared >nul 2>&1
sc delete Cloudflared >nul 2>&1

echo [*] Installing Cloudflare Tunnel Service...
cloudflared.exe service install %TOKEN%

if %errorLevel% equ 0 (
    echo.
    echo [*] Starting Cloudflared service...
    net start Cloudflared >nul 2>&1
    echo.
    echo ======================================================================
    echo [SUCCESS] Cloudflare Tunnel Service successfully CONNECTED!
    echo.
    echo Ab Cloudflare Dashboard me check karein:
    echo Status "HEALTHY" (Green) ho chuka hoga!
    echo ======================================================================
) else (
    echo.
    echo [!] Installation failed.
    echo Please make sure the token was copied using Cloudflare's Copy button.
)

echo.
pause
