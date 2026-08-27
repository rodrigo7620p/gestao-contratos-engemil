@echo off
setlocal
cd /d "%~dp0"
title Instalar servico Windows - Gestao Contratual ENGEMIL

echo ============================================================
echo  Instalacao como SERVICO DO WINDOWS (via NSSM)
echo ============================================================
echo.
echo  Isso faz o sistema iniciar sozinho com o Windows, mesmo sem
echo  ninguem logar, sem depender de deixar um terminal aberto -
echo  e resolve de vez a necessidade de reiniciar a maquina para
echo  o sistema "pegar" uma atualizacao.
echo.

if not exist "%~dp0nssm\nssm.exe" (
    echo NSSM nao encontrado em "%~dp0nssm\nssm.exe"
    echo.
    echo Baixe o NSSM em https://nssm.cc/download , extraia o arquivo
    echo nssm.exe da pasta "win64" do zip baixado, e coloque-o dentro de
    echo uma pasta chamada "nssm" aqui neste projeto, ou seja:
    echo   %~dp0nssm\nssm.exe
    echo Depois rode este script novamente.
    pause
    exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo O ambiente Python (.venv) ainda nao foi criado.
    echo Rode iniciar_sistema.bat pelo menos uma vez ANTES de instalar
    echo o servico, para o .venv ser criado e as dependencias instaladas.
    pause
    exit /b 1
)

echo Parando e removendo uma instalacao anterior do servico, se existir...
"%~dp0nssm\nssm.exe" stop GestaoContratosENGEMIL >nul 2>&1
"%~dp0nssm\nssm.exe" remove GestaoContratosENGEMIL confirm >nul 2>&1

echo Instalando o servico "GestaoContratosENGEMIL"...
"%~dp0nssm\nssm.exe" install GestaoContratosENGEMIL "%~dp0.venv\Scripts\python.exe"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL AppParameters "-m streamlit run app.py --server.headless true"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL AppDirectory "%~dp0"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL Start SERVICE_AUTO_START
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL DisplayName "Gestao de Contratos ENGEMIL"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL Description "Sistema de Gestao de Contratos ENGEMIL (Streamlit). Inicia automaticamente com o Windows."
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL AppStdout "%~dp0nssm\servico_saida.log"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL AppStderr "%~dp0nssm\servico_erros.log"
"%~dp0nssm\nssm.exe" set GestaoContratosENGEMIL AppRotateFiles 1

echo.
echo Iniciando o servico agora...
"%~dp0nssm\nssm.exe" start GestaoContratosENGEMIL

echo.
echo ============================================================
echo  Pronto! O sistema agora roda como servico do Windows.
echo ============================================================
echo  Acesse em http://localhost:8501
echo.
echo  A PARTIR DE AGORA, para reiniciar apos uma atualizacao de
echo  arquivos, use reiniciar_servico.bat em vez de
echo  iniciar_sistema.bat ou reiniciar_sistema.bat.
echo.
echo  Se algo nao funcionar, confira os arquivos de log em:
echo    %~dp0nssm\servico_saida.log
echo    %~dp0nssm\servico_erros.log
echo.
echo  IMPORTANTE: este script nao foi testado num Windows real durante
echo  o desenvolvimento (ambiente sem Windows disponivel). Teste com
echo  atencao e, se algo der errado, "%~dp0nssm\nssm.exe" remove
echo  GestaoContratosENGEMIL confirm desfaz a instalacao, voltando a
echo  usar iniciar_sistema.bat normalmente.
pause
endlocal
