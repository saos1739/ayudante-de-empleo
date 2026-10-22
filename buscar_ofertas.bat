@echo off
title Radar de Empleo - Busqueda Directa
cd /d "%~dp0"

echo ==================================================
echo   Ejecutando rastreo en portales de empleo...
echo ==================================================
echo.

set "PY=C:\Users\santi\AppData\Local\Python\bin\python.exe"
if exist "%PY%" (
    "%PY%" -m radar buscar
) else (
    python -m radar buscar
)

echo.
echo Presione cualquier tecla para salir...
pause >nul
