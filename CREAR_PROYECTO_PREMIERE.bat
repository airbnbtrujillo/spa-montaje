@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Crea el proyecto de Premiere (originales + proxies, carpetas por etapa y toma) con el metodo de AutoSync.
echo Cierra antes cualquier otro proyecto abierto en Premiere. No toques el teclado hasta que termine.
echo.
".venv\Scripts\python.exe" spa_premiere.py
echo.
pause
