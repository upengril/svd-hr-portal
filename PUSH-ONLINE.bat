@echo off
setlocal
cd /d "%~dp0"
echo ======================================================================
echo           CivMasterPro - Push Update to Online Server
echo ======================================================================
echo.
echo [*] Packaging backend and frontend into update.zip...
powershell -Command "Compress-Archive -Path backend, frontend -DestinationPath update.zip -Force"

echo.
echo [*] Transmitting update to https://svd.civmasterpro.com...
curl.exe -X POST -F "file=@update.zip" "https://svd.civmasterpro.com/api/system/push-update?token=svd_update_secret_key_2026"

echo.
if exist update.zip del update.zip
echo.
echo [+] Update successfully pushed to live server!
pause
