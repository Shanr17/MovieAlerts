@echo off
title Movie Ticket Alert Monitor (Local Runner)
cd /d "%~dp0"
echo ========================================================
echo       🎬 Movie Ticket Alert Monitor (Local Runner)
echo   Checking BookMyShow, PVR, and District every 2.5 min
echo ========================================================
echo.
python monitor.py --loop --interval 150
pause
