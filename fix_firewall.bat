@echo off
:: Check for administrative permissions
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo ============================================================
echo   ELH Management System - Windows Firewall Auto-Configurator
echo ============================================================
echo.

echo [1/3] Adding Firewall Rule for Port 8080 (Any Profile)...
netsh advfirewall firewall delete rule name="ELH Web Management (8080)" >nul 2>&1
netsh advfirewall firewall add rule name="ELH Web Management (8080)" dir=in action=allow protocol=TCP localport=8080 profile=any

echo [2/3] Allowing Python Executables on All Profiles (Private, Public, Domain)...
netsh advfirewall firewall set rule name="python.exe" new profile=any >nul 2>&1
netsh advfirewall firewall delete rule name="Python ELH Web Server" >nul 2>&1
netsh advfirewall firewall add rule name="Python ELH Web Server" dir=in action=allow program="C:\Users\Expert\AppData\Local\Python\pythoncore-3.14-64\python.exe" profile=any
netsh advfirewall firewall add rule name="Python ELH Web Server" dir=in action=allow program="G:\ELH Management System\.build-venv\Scripts\python.exe" profile=any

echo [3/3] Enabling Ping (ICMPv4) for Network Diagnostics...
netsh advfirewall firewall set rule name="File and Printer Sharing (Echo Request - ICMPv4-In)" new enable=yes profile=any >nul 2>&1
netsh advfirewall firewall add rule name="Allow ICMPv4 Ping" dir=in action=allow protocol=icmpv4:8,any profile=any >nul 2>&1

echo.
echo ============================================================
echo   Firewall configured successfully!
echo ============================================================
echo.
echo Your PC Local IP is: 192.168.1.30
echo Access URL on your mobile phone:
echo    http://192.168.1.30:8080
echo.
echo NOTE: Make sure to type "http://" and NOT "https://"
echo.
pause
