@echo off
title Restart Server (Fix Audio)
echo ===================================================
echo Restarting Pro Video Downloader...
echo (Applying Audio Fixes for Facebook/Instagram)
echo ===================================================

echo.
echo Stopping old processes...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im ProVideoApp.exe >nul 2>&1

echo.
echo [1/2] Making sure ffmpeg is detected...
if not exist "ffmpeg.exe" (
    if exist "dist\ffmpeg.exe" (
        copy "dist\ffmpeg.exe" . >nul
        echo ffmpeg.exe restored.
    )
)

echo.
echo [2/2] Starting Server...
echo A black window will open. PLEASE DO NOT CLOSE IT.
start "Pro Video Server (Keep Open)" cmd /k "python server.py"

echo Waiting for server...
timeout /t 3 /nobreak >nul

echo.
echo Opening App...
start index.html

echo.
echo ===================================================
echo DONE!
echo Try downloading Facebook/Instagram video now.
echo ===================================================
pause
