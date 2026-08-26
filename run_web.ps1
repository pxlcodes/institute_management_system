# Starts the browser version on this computer.
$ErrorActionPreference = 'Stop'
$python = 'C:\Users\Expert\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $python -m uvicorn web_main:app --host 0.0.0.0 --port 8080
