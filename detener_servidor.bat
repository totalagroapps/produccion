@echo off
echo Deteniendo servidor...
taskkill /FI "WINDOWTITLE eq ServidorProduccion*" /T /F
pause