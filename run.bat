@echo off
chcp 65001 >nul
title VideoGrabber
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found. Install it from https://www.python.org/downloads/
    echo     and check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

python main.py
if errorlevel 1 (
    echo.
    echo [!] The app exited with an error. Try: install.bat
    pause
)
