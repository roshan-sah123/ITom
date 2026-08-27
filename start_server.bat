@echo off
title ITOM Portal On-Premise Server
cd /d "%~dp0"
echo ============================================================
echo      ITOM Enterprise Portal - On-Premise Web Server
echo ============================================================
echo  Listening on:   http://0.0.0.0:8080
echo  Localhost Link: http://localhost:8080/
echo  OPS Analytics:  http://localhost:8080/ops_analytics.html
echo.
echo  Press Ctrl+C to stop the server at any time.
echo ============================================================
python -m http.server 8080 --bind 0.0.0.0
pause
