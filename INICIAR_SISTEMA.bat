@echo off
chcp 65001 > nul
title Relatorio de Aporte - Joy+ Evans

echo ========================================================
echo         RELATORIO DE APORTE - JOY+ EVANS
echo ========================================================
echo.

cd /d "%~dp0"

python --version > nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado. Instale o Python 3.10 ou superior, marcando "Add Python to PATH".
    pause
    exit /b 1
)

python -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', 8060))==0 else 1)"
if not errorlevel 1 (
    echo A porta 8060 ja esta em uso. Feche a outra janela do sistema e tente novamente.
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn, openpyxl, requests" > nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias...
    python -m pip install -r requirements-dev.txt
)

if not exist "data\aporte.sqlite3" (
    echo Primeira execucao: carregando dados iniciais da planilha...
    python -m backend.app.migrar planilha
)

echo.
echo Sistema disponivel em: http://127.0.0.1:8060
echo Para encerrar, feche esta janela.
echo.
start "" cmd /c "ping -n 4 127.0.0.1 > nul & start http://127.0.0.1:8060"
python -m uvicorn backend.app.main:criar_app --factory --host 127.0.0.1 --port 8060
pause
