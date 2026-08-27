@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Reiniciar Gestao Contratual ENGEMIL

echo Procurando processo ouvindo na porta 8501...
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8501 .*LISTENING"') do (
    echo Encerrando processo PID %%p...
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)

if "!FOUND!"=="0" (
    echo Nenhum processo estava rodando na porta 8501 - ok, prosseguindo.
) else (
    echo Processo anterior encerrado. Aguardando a porta liberar...
    timeout /t 2 >nul
)

echo.
echo Apagando cache do Python (__pycache__) para evitar codigo antigo em cache...
if exist "%~dp0__pycache__" rmdir /s /q "%~dp0__pycache__"

echo.
echo Iniciando o sistema novamente...
echo.
call "%~dp0iniciar_sistema.bat"
endlocal
