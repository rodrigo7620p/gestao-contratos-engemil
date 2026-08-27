@echo off
setlocal
cd /d "%~dp0"
title Remover servico - Gestao Contratual ENGEMIL

if not exist "%~dp0nssm\nssm.exe" (
    echo "%~dp0nssm\nssm.exe" nao encontrado - o servico provavelmente
    echo nao esta instalado.
    pause
    exit /b 1
)

echo Parando e removendo o servico GestaoContratosENGEMIL...
"%~dp0nssm\nssm.exe" stop GestaoContratosENGEMIL
"%~dp0nssm\nssm.exe" remove GestaoContratosENGEMIL confirm

echo.
echo Servico removido. O sistema voltou ao modo manual - use
echo iniciar_sistema.bat (ou reiniciar_sistema.bat) normalmente.
pause
endlocal
