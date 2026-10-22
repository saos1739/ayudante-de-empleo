@echo off
title Radar de Empleo - Panel Local
cd /d "%~dp0"

echo ==================================================
echo   Iniciando Radar de Empleo (Santiago Rojas Casas)
echo   Panel web en http://127.0.0.1:5050
echo ==================================================
echo.

set "PY=C:\Users\santi\AppData\Local\Python\bin\python.exe"
if exist "%PY%" (
    "%PY%" -m radar panel
) else (
    python -m radar panel
)

pause
