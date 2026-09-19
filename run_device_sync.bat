@echo off
title ELH Institute Device Sync Gateway
cd /d "%~dp0"
echo =========================================================
echo    ELH Institute Device Gateway - Live Sync Service
echo =========================================================
echo This service keeps the ZKTeco Biometric device and POS
echo receipt printer connected to the central ELH system.
echo Keep this window running while the institute is active.
echo =========================================================
echo.

if exist ".build-venv\Scripts\python.exe" (
    ".build-venv\Scripts\python.exe" elh_device_sync_service.py
) else (
    python elh_device_sync_service.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Device sync service exited with error code %ERRORLEVEL%.
    pause
)
