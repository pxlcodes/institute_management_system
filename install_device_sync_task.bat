@echo off
cd /d "%~dp0"
echo =========================================================
echo  Install ELH Institute Device Gateway as Scheduled Task
echo =========================================================
echo This sets up the Device Sync Service to automatically
echo launch in the background whenever Windows starts.
echo.

set SCRIPT_PATH=%~dp0run_device_sync.bat

schtasks /create /tn "ELH_Device_Sync" /tr "\"%SCRIPT_PATH%\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Scheduled Task "ELH_Device_Sync" registered successfully!
    echo It will start automatically each time the Admin logs into Windows.
) else (
    echo.
    echo [NOTE] Could not register scheduled task automatically.
    echo Please right-click this file and select 'Run as administrator'.
)

echo.
pause
