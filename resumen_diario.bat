@echo off
rem Busca ofertas y envia el resumen diario por correo (lo ejecuta el Programador de tareas de Windows).
cd /d "%~dp0"
set "PY=C:\Users\santi\AppData\Local\Python\bin\python.exe"
if exist "%PY%" (
    "%PY%" -m radar resumen >> "%LOCALAPPDATA%\RadarEmpleo\resumen.log" 2>&1
) else (
    python -m radar resumen >> "%LOCALAPPDATA%\RadarEmpleo\resumen.log" 2>&1
)
