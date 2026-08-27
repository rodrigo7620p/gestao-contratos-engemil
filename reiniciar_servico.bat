@echo off
setlocal
cd /d "%~dp0"
title Reiniciar servico - Gestao Contratual ENGEMIL

if not exist "%~dp0nssm\nssm.exe" (
    echo Este script e para quem instalou o sistema como servico do
    echo Windows via instalar_servico_windows.bat. Nao encontrei
    echo "%~dp0nssm\nssm.exe" - se voce nao instalou o servico, use
    echo reiniciar_sistema.bat em vez deste.
    pause
    exit /b 1
)

echo Apagando cache do Python (__pycache__)...
if exist "%~dp0__pycache__" rmdir /s /q "%~dp0__pycache__"

echo Reiniciando o servico GestaoContratosENGEMIL...
"%~dp0nssm\nssm.exe" restart GestaoContratosENGEMIL

echo.
echo Pronto. Acesse em http://localhost:8501
echo Se a pagina nao responder em alguns segundos, confira os logs em:
echo   %~dp0nssm\servico_erros.log
pause
endlocal
