@echo off
chcp 65001 >nul
title VideoGrabber - Get ffmpeg
cd /d "%~dp0"

if exist ffmpeg.exe (
    echo ffmpeg.exe already exists here. Nothing to do.
    pause
    exit /b 0
)

echo Downloading ffmpeg (~35 MB) - please wait...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "$ProgressPreference='SilentlyContinue';" ^
  "$u='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';" ^
  "Invoke-WebRequest -Uri $u -OutFile ffmpeg.zip;" ^
  "Expand-Archive -Path ffmpeg.zip -DestinationPath ffmpeg_tmp -Force;" ^
  "Copy-Item 'ffmpeg_tmp\ffmpeg-*-essentials\bin\ffmpeg.exe' -Destination .;" ^
  "Copy-Item 'ffmpeg_tmp\ffmpeg-*-essentials\bin\ffprobe.exe' -Destination .;" ^
  "Remove-Item ffmpeg.zip -Force; Remove-Item ffmpeg_tmp -Recurse -Force"

if exist ffmpeg.exe (
    echo.
    echo [OK] ffmpeg downloaded successfully. You are ready!
) else (
    echo.
    echo [X] Download failed. Download manually:
    echo     https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo     then copy ffmpeg.exe + ffprobe.exe from its \bin folder next to main.py
)
pause
