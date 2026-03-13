@echo off
title CONTROL SERVIDOR PRODUCCION
color 0A

:menu
cls
echo ====================================
echo      SERVIDOR PRODUCCION
echo ====================================
echo.
echo 1 - Iniciar servidor
echo 2 - Detener servidor
echo 3 - Reiniciar servidor
echo 4 - Ver logs
echo 5 - Salir
echo.
set /p opcion=Selecciona una opcion:

if %opcion%==1 goto iniciar
if %opcion%==2 goto detener
if %opcion%==3 goto reiniciar
if %opcion%==4 goto logs
if %opcion%==5 exit

goto menu


:iniciar
cls
echo Iniciando servidor...
cd /d C:\produccion_server
start "ServidorProduccion" cmd /k py -m uvicorn main:app --host 0.0.0.0 --port 8000
timeout /t 2 >nul
goto menu


:detener
cls
echo Deteniendo servidor...
taskkill /FI "WINDOWTITLE eq ServidorProduccion*" /T /F
timeout /t 2 >nul
goto menu


:reiniciar
cls
echo Reiniciando servidor...
taskkill /FI "WINDOWTITLE eq ServidorProduccion*" /T /F
timeout /t 2 >nul
cd /d C:\produccion_server
start "ServidorProduccion" cmd /k py -m uvicorn main:app --host 0.0.0.0 --port 8000
timeout /t 2 >nul
goto menu


:logs
cls
echo Mostrando procesos Python activos
echo.
tasklist | findstr python
pause
goto menu