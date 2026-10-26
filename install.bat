@echo off
chcp 65001 >nul
title VideoGrabber - Setup
cd /d "%~dp0"
echo ============================================
echo   VideoGrabber - one-time setup
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found!
    echo     1. Download Python from:  https://www.python.org/downloads/
    echo     2. During install CHECK the box:  "Add python.exe to PATH"
    echo     3. Run this file again.
    pause
    exit /b 1
)

echo [1/2] Installing/updating required packages  (PyQt6 + yt-dlp)...
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo [X] Package installation failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo [2/2] Checking ffmpeg...
if exist ffmpeg.exe (
    echo       ffmpeg found next to the app. OK.
) else (
    where ffmpeg >nul 2>nul
    if errorlevel 1 (
        echo       [!] ffmpeg NOT found. To enable best-quality merging and MP3,
        echo           run:  get-ffmpeg.bat
    ) else (
        echo       ffmpeg found in PATH. OK.
    )
)

echo.
echo ============================================
echo   Setup finished!  Now run:  run.bat
echo ============================================
pause
