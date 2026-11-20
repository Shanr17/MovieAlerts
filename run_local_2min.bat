@echo off
title Movie Ticket Alert Monitor
echo ======================================================
echo Starting Movie Ticket Alert Monitor (every 2.5 mins)
echo Press Ctrl+C to stop anytime.
echo ======================================================
python monitor.py --loop --interval 150
pause
