@echo off
cd /d "%~dp0"
echo Instalando o verificando Flask...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo No se pudieron instalar las dependencias. Revisa tu conexion a internet y Python.
  pause
  exit /b 1
)
echo Iniciando Repositorio ENSCM...
python main.py
pause
