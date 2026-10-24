@echo off
title SV DREEAMPLANNERS - HR ^& Biometric Portal
color 0A

echo ======================================================================
echo           SV DREEAMPLANNERS PRIVATE LIMITED
echo         HR ^& Biometric Management System (Port 5000)
echo ======================================================================
echo.
echo Device 2 IP: 192.168.31.111 : 4370
echo Database: PostgreSQL svd_erp_dev (Shared with SVD ERP)
echo.
echo [ACCESS URLS]
echo   - Local PC:   http://localhost:5000
echo   - Other Devices (Same Wi-Fi): http://192.168.31.37:5000
echo.
echo Starting Web Server...
cd /d "D:\svd-hr-portal"

start http://localhost:5000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000

pause
