@echo off
cd /d "%~dp0"
if exist ".build-venv\Scripts\python.exe" (
    ".build-venv\Scripts\python.exe" web_main.py
) else (
    python web_main.py
)
