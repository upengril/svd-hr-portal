@echo off
title SV DREEAMPLANNERS - Client PC Auto-Start Installer
color 0B

echo ======================================================================
echo           SV DREEAMPLANNERS PRIVATE LIMITED
echo       Client PC Silent Auto-Start ^& Background Setup
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

set "APP_DIR=%~dp0"
set "VBS_SCRIPT=%APP_DIR%scripts\run_hidden.vbs"

echo [*] Application Directory: %APP_DIR%
echo [*] Silent Launcher Script: %VBS_SCRIPT%
echo.

:: 1. Register Silent Background Task in Windows Task Scheduler
echo [1/3] Creating Auto-Start Task in Windows Task Scheduler...
schtasks /create /tn "SVD_HR_Portal_Silent" /tr "wscript.exe \"%VBS_SCRIPT%\"" /sc onlogon /rl highest /f >nul 2>&1

if %errorLevel% equ 0 (
    echo       [+] Auto-start task created successfully! (Runs silently on every PC start)
) else (
    echo       [-] Failed to create task. Falling back to Startup folder...
    set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
    copy /y "%APP_DIR%scripts\run_hidden.vbs" "%STARTUP_DIR%\SVD_HR_Portal.vbs" >nul
    echo       [+] Added to Windows Startup folder.
)

:: 2. Cloudflare Tunnel Service Check
echo.
echo [2/3] Setting up Cloudflare Tunnel Service...
where cloudflared >nul 2>&1
if %errorLevel% equ 0 (
    echo       [+] Cloudflare CLI (cloudflared) is found on this PC.
    echo.
    set /p CF_TOKEN="Enter your Cloudflare Tunnel Token (or press ENTER to skip): "
    if defined CF_TOKEN (
        echo Installing Cloudflare background service...
        cloudflared service install %CF_TOKEN%
    )
) else (
    echo       [-] Cloudflared is not installed yet.
    echo           Please install cloudflared MSI or run:
    echo           cloudflared.exe service install ^<YOUR_TOKEN^>
)

:: 3. Start the Portal Right Now
echo.
echo [3/3] Starting HR Portal in background right now...
wscript.exe "%VBS_SCRIPT%"
echo       [+] Application started silently in the background!
echo.
echo ======================================================================
echo Setup completed successfully!
echo - Web server will now start automatically whenever this PC turns on.
echo - Logs are saved in: %APP_DIR%logs\server.log
echo ======================================================================
pause
