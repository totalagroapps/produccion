@echo off
cd /d C:\produccion_server
echo Iniciando servidor...
start "ServidorProduccion" cmd /k py -m uvicorn main:app --host 0.0.0.0 --port 8000