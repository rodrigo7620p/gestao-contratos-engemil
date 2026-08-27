@echo off
cd /d "%~dp0"
if not exist "%~dp0configuracao_email.bat" (
    echo Configure primeiro o arquivo configuracao_email.bat.
    echo Use configuracao_email.exemplo.bat como modelo.
    pause
    exit /b 1
)
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo O ambiente Python ainda nao foi instalado. Execute instalar.bat primeiro.
    pause
    exit /b 1
)
icacls "%~dp0configuracao_email.bat" /inheritance:r /grant:r "%USERNAME%:F" "SYSTEM:F" >nul 2>&1
if errorlevel 1 (
    echo Aviso: nao foi possivel restringir automaticamente o arquivo de credenciais.
    echo Revise manualmente as permissoes de configuracao_email.bat.
)
set "TAREFA=ENGEMIL - Alertas Contratuais"
set "COMANDO=%~dp0executar_alertas.bat"
schtasks /Create /TN "%TAREFA%" /TR "\"%COMANDO%\"" /SC DAILY /ST 08:00 /F
if errorlevel 1 (
    echo Nao foi possivel criar a tarefa. Execute este arquivo como Administrador.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$task=Get-ScheduledTask -TaskName '%TAREFA%'; $task.Settings.StartWhenAvailable=$true; Set-ScheduledTask -InputObject $task | Out-Null" >nul 2>&1
echo.
echo Tarefa "%TAREFA%" configurada para executar todos os dias as 08:00.
echo Se o computador estiver desligado nesse horario, a tarefa iniciara quando possivel.
echo Para testar agora, execute testar_email.bat.
pause
