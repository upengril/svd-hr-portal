@echo off
title Stop SVD HR Portal Background Server
color 0C

echo Stopping SVD HR Portal background processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq SV DREEAMPLANNERS*" >nul 2>&1
wmic process where "commandline like '%%uvicorn backend.main:app%%'" delete >nul 2>&1

echo Stopped.
pause
