@echo off
chcp 65001 >nul
title VideoGrabber - Update yt-dlp
cd /d "%~dp0"
echo Updating yt-dlp (fixes for sites are released frequently)...
python -m pip install --upgrade yt-dlp
echo.
echo Done. If a site stopped working, this usually fixes it.
pause
