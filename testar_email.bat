@echo off
cd /d "%~dp0"
if not exist "%~dp0configuracao_email.bat" (
    echo O arquivo configuracao_email.bat ainda nao existe.
    echo Copie configuracao_email.exemplo.bat, renomeie e preencha os dados.
    pause
    exit /b 1
)
call "%~dp0configuracao_email.bat"
.venv\Scripts\python.exe alerts.py --smtp-status
echo.
set /p "EMAIL_TESTE=Informe o e-mail que recebera o teste: "
if "%EMAIL_TESTE%"=="" (
    echo Nenhum destinatario informado.
    pause
    exit /b 1
)
.venv\Scripts\python.exe alerts.py --test-email "%EMAIL_TESTE%"
pause
