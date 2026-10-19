@echo off
setlocal
set "PREMIERE=C:\Program Files\Adobe\Adobe Premiere Pro 2022\Adobe Premiere Pro.exe"
set "PRPROJ=C:\Claude\spa-montaje\salida\premiere\Spot Spa - base.prproj"
if not exist "%PRPROJ%" (
  echo No encuentro el proyecto base: "%PRPROJ%"
  pause
  exit /b 1
)
start "Premiere 2022 Spot Spa" "%PREMIERE%" "%PRPROJ%"
exit /b 0
