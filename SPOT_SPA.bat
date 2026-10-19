@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SPOT SPA
".venv\Scripts\python.exe" spa.py
echo.
pause
