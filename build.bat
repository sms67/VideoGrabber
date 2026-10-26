@echo off
chcp 65001 >nul
title VideoGrabber - EXE Builder
cd /d "%~dp0"
echo ============================================
echo   VideoGrabber - build a standalone .exe
echo   (needs internet, takes a few minutes)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found! Install it from https://www.python.org/downloads/
    echo     and check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo [1/3] Installing requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 ( echo [X] Failed to install requirements. & pause & exit /b 1 )

echo [2/3] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 ( echo [X] Failed to install PyInstaller. & pause & exit /b 1 )

echo [3/3] Building EXE - please wait...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name VideoGrabber --collect-all yt_dlp main.py
if errorlevel 1 (
    echo [X] Build failed. Read the messages above.
    pause
    exit /b 1
)

if exist ffmpeg.exe copy /y ffmpeg.exe dist\ >nul
if exist ffprobe.exe copy /y ffprobe.exe dist\ >nul

echo.
echo ============================================
echo   DONE!  Your app is here:   dist\VideoGrabber.exe
echo.
echo   Tip: for best quality and MP3 support,
echo        put ffmpeg.exe next to the EXE
echo        (run get-ffmpeg.bat once, then re-build)
echo ============================================
pause
