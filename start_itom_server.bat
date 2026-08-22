@echo off
title ITOM Portal On-Premise Production Server
cd /d "C:\Users\Roshan.Sah\itom"
echo ======================================================================
echo           ITOM Portal On-Premise Production Server
echo ======================================================================
echo  Listening on: http://0.0.0.0:8080
echo  Local URL:    http://localhost:8080
echo  Telemetry:    Automated 10-Minute Extraction Active
echo ======================================================================
echo  Press Ctrl+C to stop the server at any time.
echo.
python scripts\start_server.py
pause
